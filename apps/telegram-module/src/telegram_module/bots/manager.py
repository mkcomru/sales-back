from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import structlog
from aiogram import Bot, Dispatcher
from aiogram.types import Update
from aiogram.utils.token import TokenValidationError

from common import AudioConversionService
from common.transport.base_manager import BaseConnectorManager
from telegram_module.bots.handlers import create_message_handler_router
from telegram_module.bots.models import BotConfig, BotMode
from telegram_module.config import Settings
from telegram_module.services.backend import TransportBackendClient
from telegram_module.services.sales_agent import BackendInboundClient

log = structlog.get_logger(__name__)


async def _safe_async_call(coro: Awaitable[Any]) -> None:
    try:
        await coro
    except Exception as exc:  # pragma: no cover - defensive guard
        log.warning("bot.stop.failed", error=str(exc))


@dataclass
class BotRuntime:
    config: BotConfig
    mode: BotMode
    bot: Bot
    dispatcher: Dispatcher
    webhook_path: str | None
    polling_task: asyncio.Task[Any] | None = None
    shutdown_callbacks: list[Callable[[], Awaitable[Any]]] = field(default_factory=list)

    async def handle_raw_update(self, update_data: dict[str, Any]) -> None:
        update = Update.model_validate(update_data)
        await self.dispatcher.feed_update(bot=self.bot, update=update)

    async def shutdown(self) -> None:
        log.debug(
            "bot.runtime.shutdown.starting",
            connector_id=self.config.connector_id,
            mode=self.mode.value,
            has_polling_task=self.polling_task is not None,
            polling_task_done=self.polling_task.done() if self.polling_task else None,
        )

        if self.mode == BotMode.WEBHOOK:
            log.debug(
                "bot.runtime.shutdown.deleting_webhook",
                connector_id=self.config.connector_id,
            )
            await _safe_async_call(self.bot.delete_webhook())

        if self.polling_task and not self.polling_task.done():
            log.debug(
                "bot.runtime.shutdown.stopping_polling",
                connector_id=self.config.connector_id,
            )
            # Stop polling first to set the flag
            try:
                await self.dispatcher.stop_polling()
            except Exception as exc:
                log.debug("dispatcher.stop_polling.failed", error=str(exc))

            # Close session to kill network connections immediately
            # This prevents aiogram's retry logic from re-establishing
            log.debug(
                "bot.runtime.shutdown.closing_session_early",
                connector_id=self.config.connector_id,
            )
            await _safe_async_call(self.bot.session.close())

            # Now cancel the task - it should exit quickly since session is closed
            self.polling_task.cancel()
            await _safe_async_call(self.polling_task)
            log.debug(
                "bot.runtime.shutdown.polling_stopped",
                connector_id=self.config.connector_id,
            )

        for callback in self.shutdown_callbacks:
            await _safe_async_call(callback())

        # Session might already be closed for polling, but safe to call again
        log.debug(
            "bot.runtime.shutdown.closing_session",
            connector_id=self.config.connector_id,
        )
        await _safe_async_call(self.bot.session.close())
        log.debug("bot.runtime.shutdown.completed", connector_id=self.config.connector_id)


async def _dispose_partial_bot(bot: Bot | None, runtime: BotRuntime | None) -> None:
    if runtime is not None:
        if runtime.polling_task and not runtime.polling_task.done():
            try:
                await runtime.dispatcher.stop_polling()
            except Exception as exc:
                log.debug("bot.registration.cleanup.stop_polling_failed", error=str(exc))
            runtime.polling_task.cancel()
            await _safe_async_call(runtime.polling_task)
        await _safe_async_call(runtime.bot.session.close())
        return
    if bot is not None:
        await _safe_async_call(bot.session.close())


class BotManager(BaseConnectorManager[BotConfig]):
    """Manage Telegram bots lifecycle and config reloads."""

    def __init__(
        self,
        settings: Settings,
        backend: TransportBackendClient,
        sales_agent: BackendInboundClient,
    ) -> None:
        self._settings = settings
        self._backend = backend
        self._sales_agent = sales_agent
        self._audio_converter = AudioConversionService()
        self._bots: dict[str, BotRuntime] = {}
        self._lock = asyncio.Lock()

    def get(self, connector_id: str) -> BotRuntime | None:
        return self._bots.get(connector_id)

    async def reload(self) -> None:
        """Reload bots configuration from backend service."""
        # Check cancellation before starting expensive operations
        current_task = asyncio.current_task()
        if current_task is not None and current_task.cancelled():
            raise asyncio.CancelledError

        try:
            bot_configs = await self._backend.fetch_connectors()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.error("bot.reload.failed", error=str(exc))
            raise

        # Check cancellation again before acquiring lock
        current_task = asyncio.current_task()
        if current_task is not None and current_task.cancelled():
            raise asyncio.CancelledError

        async with self._lock:
            new_configs_dict = {cfg.connector_id: cfg for cfg in bot_configs}
            existing_ids = set(self._bots.keys())
            new_ids = set(new_configs_dict.keys())

            to_remove = existing_ids - new_ids
            to_add = new_ids - existing_ids
            to_update = existing_ids & new_ids

            registration_failures: list[dict[str, str]] = []

            for connector_id in to_remove:
                runtime = self._bots[connector_id]
                log.info(
                    "bot.removal.starting",
                    connector_id=connector_id,
                    mode=runtime.mode.value,
                )
                await runtime.shutdown()
                del self._bots[connector_id]
                log.info("bot.removed", connector_id=connector_id)

            for cfg in bot_configs:
                if cfg.connector_id not in to_add:
                    continue
                err = await self._register_bot(cfg)
                if err is not None:
                    registration_failures.append(
                        {
                            "connector_id": cfg.connector_id,
                            "company_id": cfg.company_id,
                            "error": err,
                        }
                    )

            for cfg in bot_configs:
                if cfg.connector_id not in to_update:
                    continue
                old_config = self._bots[cfg.connector_id].config
                if not self._config_changed(old_config, cfg):
                    continue
                connector_id = cfg.connector_id
                runtime = self._bots[connector_id]
                await runtime.shutdown()
                del self._bots[connector_id]
                err = await self._register_bot(cfg)
                if err is not None:
                    registration_failures.append(
                        {
                            "connector_id": connector_id,
                            "company_id": cfg.company_id,
                            "error": err,
                        }
                    )
                    continue
                log.info("bot.updated", connector_id=connector_id)

            if registration_failures:
                log.warning(
                    "bot.reload.registration_failures",
                    failed_count=len(registration_failures),
                    failures=registration_failures,
                )

    async def shutdown(self) -> None:
        # Try to acquire lock with timeout to avoid blocking forever
        # if reload() is stuck
        try:
            await asyncio.wait_for(self._acquire_lock_and_shutdown(), timeout=5.0)
        except TimeoutError:
            log.warning(
                "bot.shutdown.lock_timeout",
                message="Lock timeout, forcing shutdown",
            )
            # Force shutdown even if lock is held (reload will fail gracefully)
            await self._shutdown_all()

    async def _acquire_lock_and_shutdown(self) -> None:
        async with self._lock:
            await self._shutdown_all()

    async def _shutdown_all(self) -> None:
        tasks = [runtime.shutdown() for runtime in self._bots.values()]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._bots.clear()

    def _determine_default_mode(self) -> BotMode:
        value = self._settings.default_mode.lower()
        if value == BotMode.AUTO.value:
            return BotMode.WEBHOOK if self._settings.public_url is not None else BotMode.POLLING
        try:
            return BotMode(value)
        except ValueError:
            log.warning(
                "bot.mode.invalid_default",
                value=value,
                fallback="polling",
            )
            return BotMode.POLLING

    def _config_changed(self, old: BotConfig, new: BotConfig) -> bool:
        old_dict = old.model_dump(exclude={"bot_token", "webhook_secret"})
        new_dict = new.model_dump(exclude={"bot_token", "webhook_secret"})
        if old_dict != new_dict:
            return True
        if old.bot_token.get_secret_value() != new.bot_token.get_secret_value():
            return True

        old_secret = None
        if old.webhook_secret:
            old_secret = old.webhook_secret.get_secret_value()

        new_secret = None
        if new.webhook_secret:
            new_secret = new.webhook_secret.get_secret_value()

        return old_secret != new_secret

    async def _register_bot(self, config: BotConfig) -> str | None:
        default_mode = self._determine_default_mode()
        mode = config.resolved_mode(default_mode)
        token = config.bot_token.get_secret_value()
        allowed_updates = config.metadata.get("allowed_updates")

        bot: Bot | None = None
        runtime: BotRuntime | None = None

        try:
            try:
                bot = Bot(token=token)
            except TokenValidationError as exc:
                log.error(
                    "bot.registration.token_invalid",
                    connector_id=config.connector_id,
                    company_id=config.company_id,
                    error=str(exc),
                )
                return f"TokenValidationError: {exc}"

            dispatcher = Dispatcher()

            router = create_message_handler_router(
                config,
                self._sales_agent,
                self._backend,
                self._audio_converter,
            )
            dispatcher.include_router(router)

            webhook_path = config.webhook_path or f"/telegram/{config.connector_id}/webhook"

            runtime = BotRuntime(
                config=config,
                mode=mode,
                bot=bot,
                dispatcher=dispatcher,
                webhook_path=webhook_path,
            )

            if mode == BotMode.WEBHOOK:
                await self._ensure_webhook(runtime)
            else:
                await self._ensure_polling(runtime, allowed_updates)

            self._bots[config.connector_id] = runtime
            log.info(
                "bot.registered",
                connector_id=config.connector_id,
                company_id=config.company_id,
                mode=mode.value,
            )
            return None

        except asyncio.CancelledError:
            await _dispose_partial_bot(bot, runtime)
            raise
        except Exception as exc:
            await _dispose_partial_bot(bot, runtime)
            log.warning(
                "bot.registration.failed",
                connector_id=config.connector_id,
                company_id=config.company_id,
                exc_type=type(exc).__name__,
                error=str(exc),
            )
            return f"{type(exc).__name__}: {exc}"

    async def _ensure_webhook(self, runtime: BotRuntime) -> None:
        if runtime.config.webhook_secret is None:
            raise RuntimeError(
                f"Connector '{runtime.config.connector_id}' requires webhook_secret for webhook delivery mode"
            )
        public_url = self._settings.public_url
        if public_url is None:
            raise RuntimeError(
                f"Public URL must be configured to use webhook mode (connector '{runtime.config.connector_id}')"
            )
        url = f"{public_url.rstrip('/')}{runtime.webhook_path}"

        await runtime.bot.delete_webhook(drop_pending_updates=self._settings.drop_pending_on_webhook_reset)
        await runtime.bot.set_webhook(
            url=url,
            secret_token=runtime.config.webhook_secret.get_secret_value(),
            drop_pending_updates=self._settings.drop_pending_on_webhook_reset,
        )
        runtime.shutdown_callbacks.append(runtime.bot.delete_webhook)

    async def _ensure_polling(self, runtime: BotRuntime, allowed_updates: list[str] | None) -> None:
        if runtime.polling_task is not None and not runtime.polling_task.done():
            log.warning(
                "bot.polling.already_running",
                connector_id=runtime.config.connector_id,
            )
            return

        await runtime.bot.delete_webhook(drop_pending_updates=self._settings.drop_pending_on_webhook_reset)

        async def polling_task() -> None:
            try:
                # AICODE-NOTE: Disable aiogram signal handlers
                # so uvicorn keeps Ctrl+C handling.
                await runtime.dispatcher.start_polling(
                    runtime.bot,
                    allowed_updates=allowed_updates,
                    polling_timeout=self._settings.polling_timeout_s,
                    handle_signals=False,
                )
            except asyncio.CancelledError:
                log.debug(
                    "bot.polling.cancelled",
                    connector_id=runtime.config.connector_id,
                )
                raise
            except Exception as exc:  # pragma: no cover - surfaced via logs
                log.error(
                    "bot.polling.error",
                    connector_id=runtime.config.connector_id,
                    error=str(exc),
                )
                raise

        runtime.polling_task = asyncio.create_task(polling_task())
