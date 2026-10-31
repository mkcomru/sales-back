from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack, asynccontextmanager, suppress

import structlog
from fastapi import FastAPI

from common import log, setup_logging
from common.fastapi import apply_cors
from common.transport.registry import CONNECTOR_TYPE_CATALOG
from common.transport.validation import validate_connector_module
from telegram_module.api.routes import (
    admin_router,
    health_router,
    telegram_router,
    transport_router,
)
from telegram_module.bots.manager import BotManager
from telegram_module.config import Settings, get_settings
from telegram_module.lifespan.eventing import eventing_lifespan
from telegram_module.services.backend import TransportBackendClient
from telegram_module.services.sales_agent import BackendInboundClient
from telegram_module.transport.manual_broadcast import ManualBroadcastService
from telegram_module.transport.service import TransportDeliveryService

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with AsyncExitStack() as stack:
        settings: Settings = get_settings()
        setup_logging(environment=settings.app.environment, debug=settings.app.debug)

        backend_client = TransportBackendClient(settings)
        sales_agent_client = BackendInboundClient(settings)
        bot_manager = BotManager(settings, backend_client, sales_agent_client)
        transport_service = TransportDeliveryService(settings, bot_manager, backend_client)
        manual_broadcast_service = ManualBroadcastService(settings, bot_manager)

        catalog_entry = CONNECTOR_TYPE_CATALOG["telegram"]
        validate_connector_module(catalog_entry, transport_service)

        app.state.settings = settings
        app.state.bot_manager = bot_manager
        app.state.sales_agent_client = sales_agent_client
        app.state.transport_service = transport_service
        app.state.manual_broadcast_service = manual_broadcast_service

        reload_task: asyncio.Task[None] | None = None

        async def periodic_reload(interval: float) -> None:
            # AICODE-NOTE: Background reload ensures bot config stays in sync with backend.
            try:
                while True:
                    await asyncio.sleep(interval)
                    # Check if we're being cancelled before starting reload
                    current_task = asyncio.current_task()
                    if current_task is not None and current_task.cancelled():
                        raise asyncio.CancelledError
                    try:
                        await bot_manager.reload()
                    except asyncio.CancelledError:
                        # Propagate cancellation immediately
                        raise
                    except Exception as exc:  # pragma: no cover - logging side-effect
                        logger.warning("bot.reload.background_failed", error=str(exc))
            except asyncio.CancelledError:
                logger.debug("periodic_reload.cancelled")
                raise

        await bot_manager.reload()
        interval = max(settings.config_refresh_interval_s, 0.0)
        if interval > 0:
            reload_task = asyncio.create_task(periodic_reload(interval))
            app.state.reload_task = reload_task

        await stack.enter_async_context(eventing_lifespan(app))

        log.info(
            "app.start",
            environment=settings.app.environment,
        )
        try:
            yield
        finally:
            logger.info("app.shutdown.starting")
            reload_task_to_cancel = reload_task or getattr(app.state, "reload_task", None)
            if reload_task_to_cancel and not reload_task_to_cancel.done():
                reload_task_to_cancel.cancel()
                with suppress(asyncio.CancelledError):
                    await reload_task_to_cancel
            await bot_manager.shutdown()
            logger.info("app.shutdown.completed")


app = FastAPI(title="Sales Bot Telegram Module", lifespan=lifespan)
apply_cors(app, get_settings().cors)

app.include_router(transport_router)
app.include_router(admin_router)
app.include_router(health_router)
app.include_router(telegram_router)
