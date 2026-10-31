"""Tests for WappiConnectorConfig model."""

from __future__ import annotations

import pytest
from pydantic import SecretStr

from wappi_module.connectors.models import WappiConnectorConfig


class TestWappiConnectorConfig:
    def test_valid_config(self) -> None:
        config = WappiConnectorConfig(
            connector_id="test",
            company_id="123",
            wappi_token=SecretStr("token"),
            wappi_profile_id="profile123",
            channel_type="telegram",
        )

        assert config.connector_id == "test"
        assert config.company_id == "123"
        assert config.wappi_token.get_secret_value() == "token"
        assert config.wappi_profile_id == "profile123"
        assert config.channel_type == "telegram"
        assert config.metadata == {}

    def test_default_channel_type(self) -> None:
        config = WappiConnectorConfig(
            connector_id="test",
            company_id="123",
            wappi_token=SecretStr("token"),
            wappi_profile_id="profile123",
        )
        assert config.channel_type == "telegram"

    def test_company_id_normalization_from_int(self) -> None:
        config = WappiConnectorConfig(
            connector_id="test",
            company_id=456,
            wappi_token=SecretStr("token"),
            wappi_profile_id="profile123",
        )
        assert config.company_id == "456"
        assert isinstance(config.company_id, str)

    def test_connector_id_strip_whitespace(self) -> None:
        config = WappiConnectorConfig(
            connector_id="  test  ",
            company_id="123",
            wappi_token=SecretStr("token"),
            wappi_profile_id="profile123",
        )
        assert config.connector_id == "test"

    def test_company_id_strip_whitespace(self) -> None:
        config = WappiConnectorConfig(
            connector_id="test",
            company_id="  123  ",
            wappi_token=SecretStr("token"),
            wappi_profile_id="profile123",
        )
        assert config.company_id == "123"

    def test_wappi_profile_id_strip_whitespace(self) -> None:
        config = WappiConnectorConfig(
            connector_id="test",
            company_id="123",
            wappi_token=SecretStr("token"),
            wappi_profile_id="  profile123  ",
        )
        assert config.wappi_profile_id == "profile123"

    def test_empty_connector_id_raises_error(self) -> None:
        with pytest.raises(ValueError, match="connector_id must be provided"):
            WappiConnectorConfig(
                connector_id="",
                company_id="123",
                wappi_token=SecretStr("token"),
                wappi_profile_id="profile123",
            )

    def test_empty_company_id_raises_error(self) -> None:
        with pytest.raises(ValueError, match="company_id must be provided"):
            WappiConnectorConfig(
                connector_id="test",
                company_id="",
                wappi_token=SecretStr("token"),
                wappi_profile_id="profile123",
            )

    def test_empty_wappi_profile_id_raises_error(self) -> None:
        with pytest.raises(ValueError, match="wappi_profile_id must be provided"):
            WappiConnectorConfig(
                connector_id="test",
                company_id="123",
                wappi_token=SecretStr("token"),
                wappi_profile_id="",
            )

    def test_whitespace_only_connector_id_raises_error(self) -> None:
        with pytest.raises(ValueError, match="connector_id must be provided"):
            WappiConnectorConfig(
                connector_id="   ",
                company_id="123",
                wappi_token=SecretStr("token"),
                wappi_profile_id="profile123",
            )

    def test_metadata_default(self) -> None:
        config = WappiConnectorConfig(
            connector_id="test",
            company_id="123",
            wappi_token=SecretStr("token"),
            wappi_profile_id="profile123",
        )
        assert config.metadata == {}

    def test_metadata_custom(self) -> None:
        metadata = {"api_base_url": "https://custom.wappi.pro"}
        config = WappiConnectorConfig(
            connector_id="test",
            company_id="123",
            wappi_token=SecretStr("token"),
            wappi_profile_id="profile123",
            metadata=metadata,
        )
        assert config.metadata == metadata

    def test_extra_fields_ignored(self) -> None:
        config = WappiConnectorConfig(
            connector_id="test",
            company_id="123",
            wappi_token=SecretStr("token"),
            wappi_profile_id="profile123",
            extra_field="should_be_ignored",
        )
        assert not hasattr(config, "extra_field")

    def test_channel_type_none_defaults_to_telegram(self) -> None:
        config = WappiConnectorConfig(
            connector_id="test",
            company_id="123",
            wappi_token=SecretStr("token"),
            wappi_profile_id="profile123",
            channel_type=None,
        )
        assert config.channel_type == "telegram"

    def test_channel_type_strip_whitespace(self) -> None:
        config = WappiConnectorConfig(
            connector_id="test",
            company_id="123",
            wappi_token=SecretStr("token"),
            wappi_profile_id="profile123",
            channel_type="  whatsapp  ",
        )
        assert config.channel_type == "whatsapp"
