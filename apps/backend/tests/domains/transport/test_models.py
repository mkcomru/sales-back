"""Model tests for unified Connector and ConnectorApiKey."""

import hashlib

import pytest
from tortoise.exceptions import IntegrityError

from src.backend.modules.transport.models import Connector, ConnectorApiKey, ConnectorType


class TestConnectorModel:
    async def test_create_telegram_connector(self, company_factory):
        company = await company_factory()
        connector = await Connector.create(
            connector_id="tg-model-test",
            company=company,
            type=ConnectorType.TELEGRAM,
            channel_type="telegram",
            display_name="Telegram Bot",
            managed=True,
            config={"bot_token": "123:ABC"},
            enabled=True,
        )
        assert connector.id is not None
        assert connector.connector_id == "tg-model-test"
        assert connector.type == ConnectorType.TELEGRAM
        assert connector.managed is True

    async def test_create_wappi_connector(self, company_factory):
        company = await company_factory()
        connector = await Connector.create(
            connector_id="wappi-model-test",
            company=company,
            type=ConnectorType.WAPPI,
            channel_type="whatsapp",
            display_name="WhatsApp Bot",
            managed=True,
            config={
                "wappi_token": "tok",
                "wappi_profile_id": "prof",
                "transport_endpoint": "https://x.com",
            },
        )
        assert connector.type == ConnectorType.WAPPI
        assert connector.channel_type == "whatsapp"

    async def test_create_custom_connector(self, company_factory):
        company = await company_factory()
        connector = await Connector.create(
            connector_id="custom-model-test",
            company=company,
            type=ConnectorType.CUSTOM,
            channel_type="custom-channel",
            display_name="Custom Connector",
            managed=False,
            config={},
        )
        assert connector.type == ConnectorType.CUSTOM
        assert connector.managed is False

    async def test_connector_unique_connector_id(self, company_factory):
        company = await company_factory()
        await Connector.create(
            connector_id="unique-id",
            company=company,
            type=ConnectorType.TELEGRAM,
            channel_type="telegram",
            display_name="First",
            managed=True,
            config={"bot_token": "tok"},
        )
        with pytest.raises(IntegrityError):
            await Connector.create(
                connector_id="unique-id",  # Duplicate
                company=company,
                type=ConnectorType.TELEGRAM,
                channel_type="telegram",
                display_name="Second",
                managed=True,
                config={"bot_token": "tok2"},
            )

    async def test_connector_default_debounce_values(self, company_factory):
        company = await company_factory()
        connector = await Connector.create(
            connector_id="debounce-default",
            company=company,
            type=ConnectorType.TELEGRAM,
            channel_type="telegram",
            display_name="Debounce Default",
            managed=True,
            config={"bot_token": "tok"},
        )
        assert connector.debounce_window_seconds == 45
        assert connector.debounce_storage_key_template == "{connector_id}:{conversation_id}"

    async def test_connector_custom_debounce_values(self, company_factory):
        company = await company_factory()
        connector = await Connector.create(
            connector_id="debounce-custom",
            company=company,
            type=ConnectorType.TELEGRAM,
            channel_type="telegram",
            display_name="Debounce Custom",
            managed=True,
            config={"bot_token": "tok"},
            debounce_window_seconds=60,
            debounce_storage_key_template="{connector_id}:{user_id}",
        )
        assert connector.debounce_window_seconds == 60
        assert connector.debounce_storage_key_template == "{connector_id}:{user_id}"

    async def test_connector_timestamps(self, company_factory):
        company = await company_factory()
        connector = await Connector.create(
            connector_id="timestamps-test",
            company=company,
            type=ConnectorType.TELEGRAM,
            channel_type="telegram",
            display_name="Timestamps",
            managed=True,
            config={"bot_token": "tok"},
        )
        assert connector.created_at is not None
        assert connector.updated_at is not None

    async def test_connector_company_relation(self, company_factory):
        company = await company_factory()
        connector = await Connector.create(
            connector_id="relation-test",
            company=company,
            type=ConnectorType.TELEGRAM,
            channel_type="telegram",
            display_name="Relation",
            managed=True,
            config={"bot_token": "tok"},
        )
        await connector.fetch_related("company")
        assert connector.company.id == company.id


class TestConnectorApiKeyModel:
    async def test_create_api_key(self, company_factory):
        company = await company_factory()
        connector = await Connector.create(
            connector_id="key-model-test",
            company=company,
            type=ConnectorType.CUSTOM,
            channel_type="custom",
            display_name="Key Test",
            managed=False,
            config={},
        )
        key_hash = hashlib.sha256(b"sk_test_key").hexdigest()
        api_key = await ConnectorApiKey.create(
            key_hash=key_hash,
            connector=connector,
            enabled=True,
        )
        assert api_key.id is not None
        assert api_key.key_hash == key_hash
        assert api_key.enabled is True

    async def test_api_key_unique_hash(self, company_factory):
        company = await company_factory()
        connector = await Connector.create(
            connector_id="unique-hash-test",
            company=company,
            type=ConnectorType.CUSTOM,
            channel_type="custom",
            display_name="Unique Hash",
            managed=False,
            config={},
        )
        key_hash = hashlib.sha256(b"sk_duplicate").hexdigest()
        await ConnectorApiKey.create(key_hash=key_hash, connector=connector, enabled=True)
        with pytest.raises(IntegrityError):
            await ConnectorApiKey.create(key_hash=key_hash, connector=connector, enabled=True)

    async def test_api_key_connector_relation(self, company_factory):
        company = await company_factory()
        connector = await Connector.create(
            connector_id="key-relation-test",
            company=company,
            type=ConnectorType.CUSTOM,
            channel_type="custom",
            display_name="Key Relation",
            managed=False,
            config={},
        )
        api_key = await ConnectorApiKey.create(
            key_hash=hashlib.sha256(b"sk_relation").hexdigest(),
            connector=connector,
            enabled=True,
        )
        await api_key.fetch_related("connector")
        assert api_key.connector.id == connector.id

    async def test_connector_api_keys_reverse_relation(self, company_factory):
        company = await company_factory()
        connector = await Connector.create(
            connector_id="reverse-relation",
            company=company,
            type=ConnectorType.CUSTOM,
            channel_type="custom",
            display_name="Reverse Relation",
            managed=False,
            config={},
        )
        await ConnectorApiKey.create(
            key_hash=hashlib.sha256(b"sk_key1").hexdigest(),
            connector=connector,
            enabled=True,
        )
        await ConnectorApiKey.create(
            key_hash=hashlib.sha256(b"sk_key2").hexdigest(),
            connector=connector,
            enabled=True,
        )
        await connector.fetch_related("api_keys")
        assert len(connector.api_keys) == 2

    async def test_api_key_cascade_delete(self, company_factory):
        company = await company_factory()
        connector = await Connector.create(
            connector_id="cascade-delete",
            company=company,
            type=ConnectorType.CUSTOM,
            channel_type="custom",
            display_name="Cascade Delete",
            managed=False,
            config={},
        )
        api_key = await ConnectorApiKey.create(
            key_hash=hashlib.sha256(b"sk_cascade").hexdigest(),
            connector=connector,
            enabled=True,
        )
        key_id = api_key.id

        await connector.delete()

        found = await ConnectorApiKey.get_or_none(id=key_id)
        assert found is None


class TestConnectorTypeEnum:
    def test_connector_types(self):
        assert ConnectorType.TELEGRAM.value == "telegram"
        assert ConnectorType.WAPPI.value == "wappi"
        assert ConnectorType.CUSTOM.value == "custom"
