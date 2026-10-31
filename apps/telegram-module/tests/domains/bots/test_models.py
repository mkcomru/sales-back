"""Tests for BotConfig and BotMode models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from telegram_module.bots.models import BotConfig, BotMode


class TestBotMode:
    """Test BotMode enum."""

    def test_bot_mode_auto(self) -> None:
        assert BotMode.AUTO == "auto"

    def test_bot_mode_webhook(self) -> None:
        assert BotMode.WEBHOOK == "webhook"

    def test_bot_mode_polling(self) -> None:
        assert BotMode.POLLING == "polling"

    def test_bot_mode_values(self) -> None:
        values = {mode.value for mode in BotMode}
        assert values == {"auto", "webhook", "polling"}


class TestBotConfig:
    """Test BotConfig model."""

    def test_bot_config_minimal(self) -> None:
        config = BotConfig(
            connector_id="test-connector",
            company_id="test-company",
            bot_token="123456:ABC-DEF",  # pragma: allowlist secret
        )

        assert config.connector_id == "test-connector"
        assert config.company_id == "test-company"
        assert config.bot_token.get_secret_value() == "123456:ABC-DEF"
        assert config.mode == BotMode.AUTO
        assert config.channel_type == "telegram"
        assert config.webhook_secret is None
        assert config.webhook_path is None
        assert config.metadata == {}

    def test_bot_config_full(self) -> None:
        config = BotConfig(
            connector_id="test-connector",
            company_id="test-company",
            bot_token="123456:ABC-DEF",  # pragma: allowlist secret
            mode=BotMode.WEBHOOK,
            channel_type="telegram",
            webhook_secret="secret-token",  # pragma: allowlist secret
            webhook_path="/custom/webhook",
            metadata={"key": "value"},
        )

        assert config.connector_id == "test-connector"
        assert config.company_id == "test-company"
        assert config.mode == BotMode.WEBHOOK
        assert config.webhook_secret is not None
        assert config.webhook_secret.get_secret_value() == "secret-token"
        assert config.webhook_path == "/custom/webhook"
        assert config.metadata == {"key": "value"}

    def test_bot_config_connector_id_required(self) -> None:
        with pytest.raises(ValidationError):
            BotConfig(
                company_id="test-company",
                bot_token="123456:ABC-DEF",  # pragma: allowlist secret
            )

    def test_bot_config_company_id_required(self) -> None:
        with pytest.raises(ValidationError):
            BotConfig(
                connector_id="test-connector",
                bot_token="123456:ABC-DEF",  # pragma: allowlist secret
            )

    def test_bot_config_bot_token_required(self) -> None:
        with pytest.raises(ValidationError):
            BotConfig(
                connector_id="test-connector",
                company_id="test-company",
            )

    def test_bot_config_connector_id_stripped(self) -> None:
        config = BotConfig(
            connector_id="  test-connector  ",
            company_id="test-company",
            bot_token="123456:ABC-DEF",  # pragma: allowlist secret
        )

        assert config.connector_id == "test-connector"

    def test_bot_config_connector_id_empty_after_strip(self) -> None:
        with pytest.raises(ValidationError):
            BotConfig(
                connector_id="   ",
                company_id="test-company",
                bot_token="123456:ABC-DEF",  # pragma: allowlist secret
            )

    def test_bot_config_company_id_stripped(self) -> None:
        config = BotConfig(
            connector_id="test-connector",
            company_id="  123  ",
            bot_token="123456:ABC-DEF",  # pragma: allowlist secret
        )

        assert config.company_id == "123"

    def test_bot_config_company_id_empty_after_strip(self) -> None:
        with pytest.raises(ValidationError):
            BotConfig(
                connector_id="test-connector",
                company_id="   ",
                bot_token="123456:ABC-DEF",  # pragma: allowlist secret
            )

    def test_bot_config_channel_type_default(self) -> None:
        config = BotConfig(
            connector_id="test-connector",
            company_id="test-company",
            bot_token="123456:ABC-DEF",  # pragma: allowlist secret
        )

        assert config.channel_type == "telegram"

    def test_bot_config_channel_type_custom(self) -> None:
        config = BotConfig(
            connector_id="test-connector",
            company_id="test-company",
            bot_token="123456:ABC-DEF",  # pragma: allowlist secret
            channel_type="custom",
        )

        assert config.channel_type == "custom"

    def test_bot_config_channel_type_stripped(self) -> None:
        config = BotConfig(
            connector_id="test-connector",
            company_id="test-company",
            bot_token="123456:ABC-DEF",  # pragma: allowlist secret
            channel_type="  telegram  ",
        )

        assert config.channel_type == "telegram"

    def test_bot_config_channel_type_empty_fallback(self) -> None:
        config = BotConfig(
            connector_id="test-connector",
            company_id="test-company",
            bot_token="123456:ABC-DEF",  # pragma: allowlist secret
            channel_type="   ",
        )

        assert config.channel_type == "telegram"

    def test_bot_config_mode_default(self) -> None:
        config = BotConfig(
            connector_id="test-connector",
            company_id="test-company",
            bot_token="123456:ABC-DEF",  # pragma: allowlist secret
        )

        assert config.mode == BotMode.AUTO

    def test_bot_config_resolved_mode_auto_returns_default(self) -> None:
        config = BotConfig(
            connector_id="test-connector",
            company_id="test-company",
            bot_token="123456:ABC-DEF",  # pragma: allowlist secret
            mode=BotMode.AUTO,
        )

        assert config.resolved_mode(BotMode.WEBHOOK) == BotMode.WEBHOOK
        assert config.resolved_mode(BotMode.POLLING) == BotMode.POLLING

    def test_bot_config_resolved_mode_explicit(self) -> None:
        config = BotConfig(
            connector_id="test-connector",
            company_id="test-company",
            bot_token="123456:ABC-DEF",  # pragma: allowlist secret
            mode=BotMode.WEBHOOK,
        )

        assert config.resolved_mode(BotMode.POLLING) == BotMode.WEBHOOK

    def test_bot_config_extra_fields_ignored(self) -> None:
        config = BotConfig(
            connector_id="test-connector",
            company_id="test-company",
            bot_token="123456:ABC-DEF",  # pragma: allowlist secret
            extra_field="should be ignored",
        )

        assert not hasattr(config, "extra_field")
