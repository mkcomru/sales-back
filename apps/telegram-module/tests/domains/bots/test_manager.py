"""Tests for BotManager."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram import Bot
from aiogram.exceptions import TelegramUnauthorizedError
from aiogram.utils.token import TokenValidationError

from telegram_module.bots.manager import BotManager, BotRuntime
from telegram_module.bots.models import BotConfig, BotMode
from telegram_module.config import Settings


@pytest.fixture
def bot_manager(
    settings: Settings,
    mock_backend_client: AsyncMock,
    mock_sales_agent_client: AsyncMock,
) -> BotManager:
    return BotManager(settings, mock_backend_client, mock_sales_agent_client)


@pytest.fixture
def bot_config() -> BotConfig:
    return BotConfig(
        connector_id="test-connector",
        company_id="test-company",
        bot_token="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",  # noqa: E501
        # pragma: allowlist secret
        mode=BotMode.POLLING,
    )


@pytest.fixture
def bot_config_webhook() -> BotConfig:
    return BotConfig(
        connector_id="test-connector-webhook",
        company_id="test-company",
        bot_token="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",  # noqa: E501
        # pragma: allowlist secret
        mode=BotMode.WEBHOOK,
        webhook_secret="webhook-secret",  # pragma: allowlist secret
    )


class TestBotManager:
    """Test BotManager functionality."""

    def test_bot_manager_init(self, bot_manager: BotManager) -> None:
        assert bot_manager._bots == {}
        assert bot_manager._lock is not None

    def test_bot_manager_get_nonexistent(self, bot_manager: BotManager) -> None:
        result = bot_manager.get("nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_bot_manager_reload_empty(self, bot_manager: BotManager, mock_backend_client: AsyncMock) -> None:
        mock_backend_client.fetch_connectors.return_value = []

        await bot_manager.reload()

        assert len(bot_manager._bots) == 0
        mock_backend_client.fetch_connectors.assert_called_once()

    @pytest.mark.asyncio
    async def test_bot_manager_reload_adds_bot(
        self,
        bot_manager: BotManager,
        mock_backend_client: AsyncMock,
        bot_config: BotConfig,
        settings: Settings,
    ) -> None:
        mock_backend_client.fetch_connectors.return_value = [bot_config]

        with (
            patch("telegram_module.bots.manager.Bot") as mock_bot_class,
            patch("telegram_module.bots.manager.Dispatcher") as mock_dispatcher_class,
            patch("telegram_module.bots.manager.create_message_handler_router") as mock_router,
        ):
            mock_bot_instance = MagicMock(spec=Bot)
            mock_bot_class.return_value = mock_bot_instance
            mock_dispatcher_instance = MagicMock()
            mock_dispatcher_instance.start_polling = AsyncMock()
            mock_dispatcher_class.return_value = mock_dispatcher_instance
            mock_router.return_value = MagicMock()

            mock_bot_instance.delete_webhook = AsyncMock()

            await bot_manager.reload()

            assert len(bot_manager._bots) == 1
            assert "test-connector" in bot_manager._bots
            runtime = bot_manager._bots["test-connector"]
            assert runtime.config.connector_id == "test-connector"
            assert runtime.mode == BotMode.POLLING

    @pytest.mark.asyncio
    async def test_bot_manager_reload_removes_bot(
        self,
        bot_manager: BotManager,
        mock_backend_client: AsyncMock,
        bot_config: BotConfig,
    ) -> None:
        with (
            patch("telegram_module.bots.manager.Bot") as mock_bot_class,
            patch("telegram_module.bots.manager.Dispatcher") as mock_dispatcher_class,
            patch("telegram_module.bots.manager.create_message_handler_router"),
        ):
            mock_bot_instance = MagicMock()
            mock_bot_class.return_value = mock_bot_instance
            mock_bot_instance.delete_webhook = AsyncMock()
            mock_session = MagicMock()
            mock_session.close = AsyncMock()
            mock_bot_instance.session = mock_session

            mock_dispatcher_instance = MagicMock()
            mock_dispatcher_instance.stop_polling = AsyncMock()
            mock_dispatcher_instance.start_polling = AsyncMock()
            mock_dispatcher_class.return_value = mock_dispatcher_instance

            mock_backend_client.fetch_connectors.return_value = [bot_config]
            await bot_manager.reload()

            assert len(bot_manager._bots) == 1

            runtime = bot_manager._bots["test-connector"]
            polling_task = MagicMock()
            polling_task.done.return_value = True
            polling_task.cancel = MagicMock()
            runtime.polling_task = polling_task

            mock_backend_client.fetch_connectors.return_value = []
            await bot_manager.reload()

            assert len(bot_manager._bots) == 0

    @pytest.mark.asyncio
    async def test_bot_manager_reload_updates_changed_config(
        self,
        bot_manager: BotManager,
        mock_backend_client: AsyncMock,
        bot_config: BotConfig,
    ) -> None:
        with (
            patch("telegram_module.bots.manager.Bot") as mock_bot_class,
            patch("telegram_module.bots.manager.Dispatcher") as mock_dispatcher_class,
            patch("telegram_module.bots.manager.create_message_handler_router"),
        ):
            mock_bot_instance = MagicMock()
            mock_bot_class.return_value = mock_bot_instance
            mock_bot_instance.delete_webhook = AsyncMock()
            mock_session = MagicMock()
            mock_session.close = AsyncMock()
            mock_bot_instance.session = mock_session

            mock_dispatcher_instance = MagicMock()
            mock_dispatcher_instance.stop_polling = AsyncMock()
            mock_dispatcher_instance.start_polling = AsyncMock()
            mock_dispatcher_class.return_value = mock_dispatcher_instance

            mock_backend_client.fetch_connectors.return_value = [bot_config]
            await bot_manager.reload()

            runtime = bot_manager._bots["test-connector"]
            polling_task = MagicMock()
            polling_task.done.return_value = True
            polling_task.cancel = MagicMock()
            runtime.polling_task = polling_task

            updated_config = BotConfig(
                connector_id="test-connector",
                company_id="test-company",
                bot_token="987654:XYZ-ABC",  # pragma: allowlist secret
                mode=BotMode.POLLING,
            )

            mock_backend_client.fetch_connectors.return_value = [updated_config]
            await bot_manager.reload()

            runtime = bot_manager._bots["test-connector"]
            assert runtime.config.bot_token.get_secret_value() == "987654:XYZ-ABC"

    @pytest.mark.asyncio
    async def test_bot_manager_reload_skips_unchanged_config(
        self,
        bot_manager: BotManager,
        mock_backend_client: AsyncMock,
        bot_config: BotConfig,
    ) -> None:
        with (
            patch("telegram_module.bots.manager.Bot") as mock_bot_class,
            patch("telegram_module.bots.manager.Dispatcher"),
            patch("telegram_module.bots.manager.create_message_handler_router"),
        ):
            mock_bot_instance = MagicMock(spec=Bot)
            mock_bot_class.return_value = mock_bot_instance
            mock_bot_instance.delete_webhook = AsyncMock()

            mock_backend_client.fetch_connectors.return_value = [bot_config]
            await bot_manager.reload()

            first_runtime = bot_manager._bots["test-connector"]

            mock_backend_client.fetch_connectors.return_value = [bot_config]
            await bot_manager.reload()

            second_runtime = bot_manager._bots["test-connector"]
            assert first_runtime is second_runtime

    @pytest.mark.asyncio
    async def test_bot_manager_reload_invalid_token(
        self,
        bot_manager: BotManager,
        mock_backend_client: AsyncMock,
        bot_config: BotConfig,
    ) -> None:
        with patch("telegram_module.bots.manager.Bot") as mock_bot_class:
            mock_bot_class.side_effect = TokenValidationError("Invalid token")

            mock_backend_client.fetch_connectors.return_value = [bot_config]

            await bot_manager.reload()

            assert len(bot_manager._bots) == 0

    @pytest.mark.asyncio
    async def test_bot_manager_reload_one_bot_failure_does_not_block_others(
        self,
        bot_manager: BotManager,
        mock_backend_client: AsyncMock,
        bot_config: BotConfig,
    ) -> None:
        bad_config = BotConfig(
            connector_id="bad-connector",
            company_id="bad-company",
            bot_token="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",  # noqa: E501
            # pragma: allowlist secret
            mode=BotMode.POLLING,
        )

        delete_calls = 0

        async def delete_webhook_side_effect(*args: object, **kwargs: object) -> None:
            nonlocal delete_calls
            delete_calls += 1
            if delete_calls == 2:
                raise TelegramUnauthorizedError(method=MagicMock(), message="Unauthorized")

        with (
            patch("telegram_module.bots.manager.Bot") as mock_bot_class,
            patch("telegram_module.bots.manager.Dispatcher") as mock_dispatcher_class,
            patch("telegram_module.bots.manager.create_message_handler_router") as mock_router,
        ):
            mock_dispatcher_instance = MagicMock()
            mock_dispatcher_instance.start_polling = AsyncMock()
            mock_dispatcher_class.return_value = mock_dispatcher_instance
            mock_router.return_value = MagicMock()

            def make_bot(*args: object, **kwargs: object) -> MagicMock:
                inst = MagicMock(spec=Bot)
                inst.delete_webhook = AsyncMock(side_effect=delete_webhook_side_effect)
                inst.session = MagicMock()
                inst.session.close = AsyncMock()
                return inst

            mock_bot_class.side_effect = make_bot

            mock_backend_client.fetch_connectors.return_value = [bot_config, bad_config]

            await bot_manager.reload()

            assert len(bot_manager._bots) == 1
            assert "test-connector" in bot_manager._bots
            assert "bad-connector" not in bot_manager._bots

    @pytest.mark.asyncio
    async def test_bot_manager_reload_update_failure_drops_connector(
        self,
        bot_manager: BotManager,
        mock_backend_client: AsyncMock,
        bot_config: BotConfig,
    ) -> None:
        with (
            patch("telegram_module.bots.manager.Bot") as mock_bot_class,
            patch("telegram_module.bots.manager.Dispatcher") as mock_dispatcher_class,
            patch("telegram_module.bots.manager.create_message_handler_router"),
        ):
            mock_bot_instance = MagicMock()
            mock_bot_class.return_value = mock_bot_instance
            mock_bot_instance.delete_webhook = AsyncMock()
            mock_session = MagicMock()
            mock_session.close = AsyncMock()
            mock_bot_instance.session = mock_session

            mock_dispatcher_instance = MagicMock()
            mock_dispatcher_instance.stop_polling = AsyncMock()
            mock_dispatcher_instance.start_polling = AsyncMock()
            mock_dispatcher_class.return_value = mock_dispatcher_instance

            mock_backend_client.fetch_connectors.return_value = [bot_config]
            await bot_manager.reload()

            runtime = bot_manager._bots["test-connector"]
            polling_task = MagicMock()
            polling_task.done.return_value = True
            polling_task.cancel = MagicMock()
            runtime.polling_task = polling_task

            updated_config = BotConfig(
                connector_id="test-connector",
                company_id="test-company",
                bot_token="987654:XYZ-ABC",  # pragma: allowlist secret
                mode=BotMode.POLLING,
            )

            failing = MagicMock()
            failing.delete_webhook = AsyncMock(
                side_effect=TelegramUnauthorizedError(method=MagicMock(), message="Unauthorized")
            )
            failing.session = MagicMock()
            failing.session.close = AsyncMock()
            mock_bot_class.return_value = failing

            mock_backend_client.fetch_connectors.return_value = [updated_config]
            await bot_manager.reload()

            assert "test-connector" not in bot_manager._bots

    @pytest.mark.asyncio
    async def test_bot_manager_reload_backend_error(
        self,
        bot_manager: BotManager,
        mock_backend_client: AsyncMock,
    ) -> None:
        from telegram_module.services.backend import TransportBackendClientError

        mock_backend_client.fetch_connectors.side_effect = TransportBackendClientError("Backend error")

        with pytest.raises(TransportBackendClientError):
            await bot_manager.reload()

    @pytest.mark.asyncio
    async def test_bot_manager_shutdown(
        self,
        bot_manager: BotManager,
        mock_backend_client: AsyncMock,
        bot_config: BotConfig,
    ) -> None:
        with (
            patch("telegram_module.bots.manager.Bot") as mock_bot_class,
            patch("telegram_module.bots.manager.Dispatcher") as mock_dispatcher_class,
            patch("telegram_module.bots.manager.create_message_handler_router"),
        ):
            mock_bot_instance = MagicMock()
            mock_bot_class.return_value = mock_bot_instance
            mock_bot_instance.delete_webhook = AsyncMock()
            mock_session = MagicMock()
            mock_session.close = AsyncMock()
            mock_bot_instance.session = mock_session

            mock_dispatcher_instance = MagicMock()
            mock_dispatcher_instance.stop_polling = AsyncMock()
            mock_dispatcher_instance.start_polling = AsyncMock()
            mock_dispatcher_class.return_value = mock_dispatcher_instance

            mock_backend_client.fetch_connectors.return_value = [bot_config]
            await bot_manager.reload()

            runtime = bot_manager._bots["test-connector"]
            polling_task = MagicMock()
            polling_task.done.return_value = True
            polling_task.cancel = MagicMock()
            runtime.polling_task = polling_task

            await bot_manager.shutdown()

            assert len(bot_manager._bots) == 0
            mock_session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_bot_manager_determine_default_mode_auto_with_public_url(
        self,
        settings: Settings,
        mock_backend_client: AsyncMock,
        mock_sales_agent_client: AsyncMock,
    ) -> None:
        settings.public_url = "https://example.com"
        settings.default_mode = "auto"

        manager = BotManager(settings, mock_backend_client, mock_sales_agent_client)

        mode = manager._determine_default_mode()
        assert mode == BotMode.WEBHOOK

    @pytest.mark.asyncio
    async def test_bot_manager_determine_default_mode_auto_without_public_url(
        self,
        settings: Settings,
        mock_backend_client: AsyncMock,
        mock_sales_agent_client: AsyncMock,
    ) -> None:
        settings.public_url = None
        settings.default_mode = "auto"

        manager = BotManager(settings, mock_backend_client, mock_sales_agent_client)

        mode = manager._determine_default_mode()
        assert mode == BotMode.POLLING

    @pytest.mark.asyncio
    async def test_bot_manager_determine_default_mode_explicit(
        self,
        settings: Settings,
        mock_backend_client: AsyncMock,
        mock_sales_agent_client: AsyncMock,
    ) -> None:
        settings.default_mode = "webhook"

        manager = BotManager(settings, mock_backend_client, mock_sales_agent_client)

        mode = manager._determine_default_mode()
        assert mode == BotMode.WEBHOOK

    @pytest.mark.asyncio
    async def test_bot_manager_determine_default_mode_invalid_fallback(
        self,
        settings: Settings,
        mock_backend_client: AsyncMock,
        mock_sales_agent_client: AsyncMock,
    ) -> None:
        settings.default_mode = "invalid"

        manager = BotManager(settings, mock_backend_client, mock_sales_agent_client)

        mode = manager._determine_default_mode()
        assert mode == BotMode.POLLING

    @pytest.mark.asyncio
    async def test_bot_manager_config_changed_token(self, bot_manager: BotManager, bot_config: BotConfig) -> None:
        new_config = BotConfig(
            connector_id="test-connector",
            company_id="test-company",
            bot_token="different-token",  # pragma: allowlist secret
            mode=BotMode.POLLING,
        )

        assert bot_manager._config_changed(bot_config, new_config) is True

    @pytest.mark.asyncio
    async def test_bot_manager_config_changed_webhook_secret(
        self, bot_manager: BotManager, bot_config: BotConfig
    ) -> None:
        new_config = BotConfig(
            connector_id="test-connector",
            company_id="test-company",
            bot_token="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",  # noqa: E501
            # pragma: allowlist secret
            mode=BotMode.POLLING,
            webhook_secret="different-secret",  # pragma: allowlist secret
        )

        assert bot_manager._config_changed(bot_config, new_config) is True

    @pytest.mark.asyncio
    async def test_bot_manager_config_unchanged(self, bot_manager: BotManager, bot_config: BotConfig) -> None:
        new_config = BotConfig(
            connector_id="test-connector",
            company_id="test-company",
            bot_token="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",  # noqa: E501
            # pragma: allowlist secret
            mode=BotMode.POLLING,
        )

        assert bot_manager._config_changed(bot_config, new_config) is False


class TestBotRuntime:
    """Test BotRuntime functionality."""

    @pytest.mark.asyncio
    async def test_bot_runtime_handle_raw_update(
        self, bot_config: BotConfig, mock_sales_agent_client: AsyncMock
    ) -> None:
        with (
            patch("telegram_module.bots.manager.Bot") as mock_bot_class,
            patch("telegram_module.bots.manager.Dispatcher") as mock_dispatcher_class,
        ):
            mock_bot_instance = MagicMock(spec=Bot)
            mock_bot_class.return_value = mock_bot_instance
            mock_dispatcher_instance = MagicMock()
            mock_dispatcher_instance.feed_update = AsyncMock()
            mock_dispatcher_class.return_value = mock_dispatcher_instance

            runtime = BotRuntime(
                config=bot_config,
                mode=BotMode.POLLING,
                bot=mock_bot_instance,
                dispatcher=mock_dispatcher_instance,
                webhook_path=None,
            )

            update_data = {
                "update_id": 123,
                "message": {
                    "message_id": 1,
                    "date": 1234567890,
                    "text": "test",
                    "chat": {"id": 123, "type": "private"},
                    "from": {"id": 456, "is_bot": False, "first_name": "Test"},
                },
            }

            await runtime.handle_raw_update(update_data)

            mock_dispatcher_instance.feed_update.assert_called_once()

    @pytest.mark.asyncio
    async def test_bot_runtime_shutdown_webhook(
        self, bot_config_webhook: BotConfig, mock_sales_agent_client: AsyncMock
    ) -> None:
        with (
            patch("telegram_module.bots.manager.Bot") as mock_bot_class,
            patch("telegram_module.bots.manager.Dispatcher") as mock_dispatcher_class,
        ):
            mock_bot_instance = MagicMock()
            mock_bot_class.return_value = mock_bot_instance
            mock_bot_instance.delete_webhook = AsyncMock()
            mock_session = MagicMock()
            mock_session.close = AsyncMock()
            mock_bot_instance.session = mock_session

            mock_dispatcher_instance = MagicMock()
            mock_dispatcher_class.return_value = mock_dispatcher_instance

            runtime = BotRuntime(
                config=bot_config_webhook,
                mode=BotMode.WEBHOOK,
                bot=mock_bot_instance,
                dispatcher=mock_dispatcher_instance,
                webhook_path="/webhook",
            )

            await runtime.shutdown()

            mock_bot_instance.delete_webhook.assert_called_once()
            mock_session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_bot_runtime_shutdown_polling(
        self, bot_config: BotConfig, mock_sales_agent_client: AsyncMock
    ) -> None:
        with (
            patch("telegram_module.bots.manager.Bot") as mock_bot_class,
            patch("telegram_module.bots.manager.Dispatcher") as mock_dispatcher_class,
        ):
            mock_bot_instance = MagicMock()
            mock_bot_class.return_value = mock_bot_instance
            mock_bot_instance.delete_webhook = AsyncMock()
            mock_session = MagicMock()
            mock_session.close = AsyncMock()
            mock_bot_instance.session = mock_session

            mock_dispatcher_instance = MagicMock()
            mock_dispatcher_instance.stop_polling = AsyncMock()
            mock_dispatcher_instance.start_polling = AsyncMock()
            mock_dispatcher_class.return_value = mock_dispatcher_instance

            runtime = BotRuntime(
                config=bot_config,
                mode=BotMode.POLLING,
                bot=mock_bot_instance,
                dispatcher=mock_dispatcher_instance,
                webhook_path=None,
            )

            polling_task = MagicMock()
            polling_task.done = MagicMock(return_value=False)
            polling_task.cancel = MagicMock()

            async def mock_await():
                pass

            polling_task.__await__ = lambda: mock_await().__await__()
            runtime.polling_task = polling_task

            await runtime.shutdown()

            polling_task.cancel.assert_called_once()
            mock_dispatcher_instance.stop_polling.assert_called_once()
            # Session is closed twice: once early to kill connections, once at end
            assert mock_session.close.call_count == 2
