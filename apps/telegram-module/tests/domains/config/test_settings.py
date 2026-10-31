"""Tests for Settings configuration."""

from __future__ import annotations

from telegram_module.config import Settings, get_settings


class TestSettings:
    """Test Settings initialization and configuration."""

    def test_get_settings_returns_instance(self) -> None:
        get_settings.cache_clear()
        settings = get_settings()

        assert isinstance(settings, Settings)

    def test_get_settings_cached(self) -> None:
        get_settings.cache_clear()
        settings1 = get_settings()
        settings2 = get_settings()

        assert settings1 is settings2

    def test_settings_backend_url(self, settings: Settings) -> None:
        assert settings.backend.url is not None
        assert isinstance(settings.backend.url, str)

    def test_settings_sales_agent_url(self, settings: Settings) -> None:
        assert settings.sales_agent_url is not None
        assert hasattr(settings.sales_agent_url, "__str__")

    def test_settings_service_api_key(self, settings: Settings) -> None:
        assert settings.service.api_key is not None

    def test_settings_default_mode(self, settings: Settings) -> None:
        assert settings.default_mode is not None
        assert isinstance(settings.default_mode, str)

    def test_settings_public_url_optional(self, settings: Settings) -> None:
        assert hasattr(settings, "public_url")

    def test_settings_config_refresh_interval(self, settings: Settings) -> None:
        assert hasattr(settings, "config_refresh_interval_s")
        assert isinstance(settings.config_refresh_interval_s, (int, float))

    def test_settings_polling_timeout(self, settings: Settings) -> None:
        assert hasattr(settings, "polling_timeout_s")
        assert isinstance(settings.polling_timeout_s, (int, float))

    def test_settings_max_delivery_attempts(self, settings: Settings) -> None:
        assert hasattr(settings, "max_delivery_attempts")
        assert isinstance(settings.max_delivery_attempts, int)
        assert settings.max_delivery_attempts > 0

    def test_settings_request_timeout(self, settings: Settings) -> None:
        assert hasattr(settings, "request_timeout_s")
        assert isinstance(settings.request_timeout_s, (int, float))

    def test_settings_drop_pending_on_webhook_reset(self, settings: Settings) -> None:
        assert hasattr(settings, "drop_pending_on_webhook_reset")
        assert isinstance(settings.drop_pending_on_webhook_reset, bool)
