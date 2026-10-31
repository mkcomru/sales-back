"""Service tests for unified Connector model."""

import hashlib

import pytest

from src.backend.modules.companies.exceptions import CompanyNotFoundError
from src.backend.modules.transport.exceptions import ConnectorNotFoundError
from src.backend.modules.transport.models import Connector, ConnectorApiKey, ConnectorType
from src.backend.modules.transport.schemas import (
    ConnectorCreateRequest,
    ConnectorTypeEnum,
    ConnectorUpdateRequest,
)
from src.backend.modules.transport.service import ConnectorsService


class TestConnectorsServiceList:
    async def test_list_connectors_empty(self):
        service = ConnectorsService()
        result = await service.list_connectors()
        assert result == []

    async def test_list_connectors_with_data(self, company_factory):
        service = ConnectorsService()
        company = await company_factory()
        await Connector.create(
            connector_id="tg-bot-1",
            company=company,
            type=ConnectorType.TELEGRAM,
            channel_type="telegram",
            display_name="Test Bot",
            managed=True,
            config={"bot_token": "token123"},
            enabled=True,
        )
        result = await service.list_connectors()
        assert len(result) == 1
        assert result[0].connector_id == "tg-bot-1"

    async def test_list_by_company(self, company_factory):
        service = ConnectorsService()
        company1 = await company_factory()
        company2 = await company_factory()

        await Connector.create(
            connector_id="company1-bot",
            company=company1,
            type=ConnectorType.TELEGRAM,
            channel_type="telegram",
            display_name="Company 1 Bot",
            managed=True,
            config={"bot_token": "token1"},
        )
        await Connector.create(
            connector_id="company2-bot",
            company=company2,
            type=ConnectorType.TELEGRAM,
            channel_type="telegram",
            display_name="Company 2 Bot",
            managed=True,
            config={"bot_token": "token2"},
        )

        result = await service.list_by_company(company1.id)
        assert len(result) == 1
        assert result[0].connector_id == "company1-bot"


class TestConnectorsServiceGet:
    async def test_get_connector_success(self, company_factory):
        service = ConnectorsService()
        company = await company_factory()
        connector = await Connector.create(
            connector_id="get-test",
            company=company,
            type=ConnectorType.TELEGRAM,
            channel_type="telegram",
            display_name="Get Test Bot",
            managed=True,
            config={"bot_token": "token"},
        )
        result = await service.get_connector(connector.id)
        assert result.id == connector.id
        assert result.connector_id == "get-test"

    async def test_get_connector_not_found(self):
        service = ConnectorsService()
        with pytest.raises(ConnectorNotFoundError):
            await service.get_connector(99999)

    async def test_get_by_connector_id(self, company_factory):
        service = ConnectorsService()
        company = await company_factory()
        await Connector.create(
            connector_id="public-id-test",
            company=company,
            type=ConnectorType.WAPPI,
            channel_type="whatsapp",
            display_name="WhatsApp Bot",
            managed=True,
            config={"wappi_token": "tok", "wappi_profile_id": "prof", "transport_endpoint": "https://x.com"},
        )
        result = await service.get_by_connector_id("public-id-test")
        assert result is not None
        assert result.connector_id == "public-id-test"

    async def test_get_by_connector_id_not_found(self):
        service = ConnectorsService()
        result = await service.get_by_connector_id("non-existent")
        assert result is None


class TestConnectorsServiceCreate:
    async def test_create_telegram_connector(self, company_factory):
        service = ConnectorsService()
        company = await company_factory()
        payload = ConnectorCreateRequest(
            connector_id="new-tg-bot",
            company_id=company.id,
            type=ConnectorTypeEnum.TELEGRAM,
            channel_type="telegram",
            display_name="New Telegram Bot",
            managed=True,
            config={"bot_token": "123:ABC", "mode": "auto"},
            enabled=True,
        )
        result = await service.create_connector(payload)
        assert result.connector_id == "new-tg-bot"
        assert result.company_id == company.id
        assert result.type == ConnectorTypeEnum.TELEGRAM
        assert "bot_token" not in result.config

    async def test_create_wappi_connector(self, company_factory):
        service = ConnectorsService()
        company = await company_factory()
        payload = ConnectorCreateRequest(
            connector_id="new-wappi",
            company_id=company.id,
            type=ConnectorTypeEnum.WAPPI,
            channel_type="whatsapp",
            display_name="WhatsApp Connector",
            managed=True,
            config={
                "wappi_token": "wappi-token",
                "wappi_profile_id": "profile-123",
                "transport_endpoint": "https://wappi.example.com",
            },
            enabled=True,
        )
        result = await service.create_connector(payload)
        assert result.connector_id == "new-wappi"
        assert result.type == ConnectorTypeEnum.WAPPI
        assert result.channel_type == "whatsapp"

    async def test_create_custom_connector(self, company_factory):
        service = ConnectorsService()
        company = await company_factory()
        payload = ConnectorCreateRequest(
            connector_id="custom-connector",
            company_id=company.id,
            type=ConnectorTypeEnum.CUSTOM,
            channel_type="custom-channel",
            display_name="Customer's Custom Bot",
            managed=False,
            config={},
            enabled=True,
        )
        result = await service.create_connector(payload)
        assert result.connector_id == "custom-connector"
        assert result.type == ConnectorTypeEnum.CUSTOM
        assert result.managed is False

    async def test_create_connector_company_not_found(self):
        service = ConnectorsService()
        payload = ConnectorCreateRequest(
            connector_id="orphan",
            company_id=99999,
            type=ConnectorTypeEnum.TELEGRAM,
            channel_type="telegram",
            display_name="Orphan Bot",
            managed=True,
            config={"bot_token": "token"},
        )
        with pytest.raises(CompanyNotFoundError):
            await service.create_connector(payload)


class TestConnectorsServiceUpdate:
    async def test_update_connector_success(self, company_factory):
        service = ConnectorsService()
        company = await company_factory()
        connector = await Connector.create(
            connector_id="update-test",
            company=company,
            type=ConnectorType.TELEGRAM,
            channel_type="telegram",
            display_name="Original Name",
            managed=True,
            config={"bot_token": "original"},
        )
        payload = ConnectorUpdateRequest(
            display_name="Updated Name",
            enabled=False,
            config={"bot_token": "updated"},
        )
        result = await service.update_connector(connector.id, payload)
        assert result.display_name == "Updated Name"
        assert result.enabled is False
        assert "bot_token" not in result.config

    async def test_update_connector_not_found(self):
        service = ConnectorsService()
        payload = ConnectorUpdateRequest(display_name="Updated")
        with pytest.raises(ConnectorNotFoundError):
            await service.update_connector(99999, payload)

    async def test_update_config_preserves_secrets(self, company_factory):
        service = ConnectorsService()
        company = await company_factory()
        connector = await Connector.create(
            connector_id="preserve-secret-test",
            company=company,
            type=ConnectorType.TELEGRAM,
            channel_type="telegram",
            display_name="Secret Preserve Test",
            managed=True,
            config={"bot_token": "secret-token", "mode": "auto"},
        )
        # Encrypt the initial config as the service would
        await service.connectors_repo.update_connector(
            connector.id,
            {"config": service._encrypt_config(ConnectorType.TELEGRAM, {"bot_token": "secret-token", "mode": "auto"})},
        )
        payload = ConnectorUpdateRequest(config={"mode": "polling"})
        await service.update_connector(connector.id, payload)

        refreshed = await Connector.get(id=connector.id)
        decrypted = service._decrypt_config(ConnectorType.TELEGRAM, dict(refreshed.config))
        assert decrypted["bot_token"] == "secret-token"
        assert decrypted["mode"] == "polling"

    async def test_update_connector_debounce_config(self, company_factory):
        service = ConnectorsService()
        company = await company_factory()
        connector = await Connector.create(
            connector_id="debounce-test",
            company=company,
            type=ConnectorType.TELEGRAM,
            channel_type="telegram",
            display_name="Debounce Test",
            managed=True,
            config={"bot_token": "tok"},
            debounce_window_seconds=45,
        )
        payload = ConnectorUpdateRequest(
            debounce_window_seconds=60,
            debounce_storage_key_template="{connector_id}:{user_id}",
        )
        result = await service.update_connector(connector.id, payload)
        assert result.debounce_window_seconds == 60
        assert result.debounce_storage_key_template == "{connector_id}:{user_id}"


class TestConnectorsServiceDelete:
    async def test_delete_connector_success(self, company_factory):
        service = ConnectorsService()
        company = await company_factory()
        connector = await Connector.create(
            connector_id="delete-test",
            company=company,
            type=ConnectorType.TELEGRAM,
            channel_type="telegram",
            display_name="Delete Me",
            managed=True,
            config={"bot_token": "tok"},
        )
        await service.delete_connector(connector.id)
        found = await Connector.get_or_none(id=connector.id)
        assert found is None

    async def test_delete_connector_not_found(self):
        service = ConnectorsService()
        with pytest.raises(ConnectorNotFoundError):
            await service.delete_connector(99999)


class TestConnectorContext:
    async def test_get_context_by_connector_id_success(self, company_factory):
        service = ConnectorsService()
        company = await company_factory()
        await Connector.create(
            connector_id="context-test",
            company=company,
            type=ConnectorType.TELEGRAM,
            channel_type="telegram",
            display_name="Context Test",
            managed=True,
            config={"bot_token": "tok"},
            enabled=True,
            debounce_window_seconds=30,
            debounce_storage_key_template="{connector_id}:{conversation_id}",
        )
        context = await service.get_context_by_connector_id("context-test")
        assert context.connector_id == "context-test"
        assert context.company_id == company.id
        assert context.channel_type == "telegram"
        assert context.debounce.window_seconds == 30

    async def test_get_context_by_connector_id_not_found(self):
        service = ConnectorsService()
        with pytest.raises(ConnectorNotFoundError):
            await service.get_context_by_connector_id("non-existent")

    async def test_get_context_by_connector_id_disabled(self, company_factory):
        service = ConnectorsService()
        company = await company_factory()
        await Connector.create(
            connector_id="disabled-connector",
            company=company,
            type=ConnectorType.TELEGRAM,
            channel_type="telegram",
            display_name="Disabled",
            managed=True,
            config={"bot_token": "tok"},
            enabled=False,
        )
        with pytest.raises(ConnectorNotFoundError):
            await service.get_context_by_connector_id("disabled-connector")


class TestApiKeyValidation:
    async def test_validate_api_key_success(self, company_factory):
        service = ConnectorsService()
        company = await company_factory()
        connector = await Connector.create(
            connector_id="api-key-test",
            company=company,
            type=ConnectorType.CUSTOM,
            channel_type="custom",
            display_name="Custom Connector",
            managed=False,
            config={},
            enabled=True,
        )
        # Create API key directly for testing
        raw_key = "sk_test_key_12345"
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        await ConnectorApiKey.create(
            key_hash=key_hash,
            connector=connector,
            enabled=True,
        )
        context = await service.validate_api_key(raw_key)
        assert context.connector_id == "api-key-test"
        assert context.company_id == company.id

    async def test_validate_api_key_invalid_prefix(self):
        service = ConnectorsService()
        with pytest.raises(ConnectorNotFoundError):
            await service.validate_api_key("invalid_key_no_prefix")

    async def test_validate_api_key_not_found(self):
        service = ConnectorsService()
        with pytest.raises(ConnectorNotFoundError):
            await service.validate_api_key("sk_nonexistent_key")

    async def test_validate_api_key_disabled_key(self, company_factory):
        service = ConnectorsService()
        company = await company_factory()
        connector = await Connector.create(
            connector_id="disabled-key-test",
            company=company,
            type=ConnectorType.CUSTOM,
            channel_type="custom",
            display_name="Disabled Key Connector",
            managed=False,
            config={},
            enabled=True,
        )
        raw_key = "sk_disabled_key_test"
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        await ConnectorApiKey.create(
            key_hash=key_hash,
            connector=connector,
            enabled=False,
        )
        with pytest.raises(ConnectorNotFoundError):
            await service.validate_api_key(raw_key)

    async def test_validate_api_key_disabled_connector(self, company_factory):
        service = ConnectorsService()
        company = await company_factory()
        connector = await Connector.create(
            connector_id="disabled-connector-key",
            company=company,
            type=ConnectorType.CUSTOM,
            channel_type="custom",
            display_name="Disabled Connector",
            managed=False,
            config={},
            enabled=False,
        )
        raw_key = "sk_connector_disabled"
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        await ConnectorApiKey.create(
            key_hash=key_hash,
            connector=connector,
            enabled=True,
        )
        with pytest.raises(ConnectorNotFoundError):
            await service.validate_api_key(raw_key)


class TestApiKeyManagement:
    async def test_create_api_key(self, company_factory):
        service = ConnectorsService()
        company = await company_factory()
        connector = await Connector.create(
            connector_id="key-create-test",
            company=company,
            type=ConnectorType.CUSTOM,
            channel_type="custom",
            display_name="Key Create Test",
            managed=False,
            config={},
        )
        result = await service.create_api_key(connector.id)
        assert result.connector_id == "key-create-test"
        assert result.raw_key.startswith("sk_")
        assert len(result.raw_key) > 10

    async def test_create_api_key_connector_not_found(self):
        service = ConnectorsService()
        with pytest.raises(ConnectorNotFoundError):
            await service.create_api_key(99999)

    async def test_list_api_keys(self, company_factory):
        service = ConnectorsService()
        company = await company_factory()
        connector = await Connector.create(
            connector_id="list-keys-test",
            company=company,
            type=ConnectorType.CUSTOM,
            channel_type="custom",
            display_name="List Keys Test",
            managed=False,
            config={},
        )
        await service.create_api_key(connector.id)
        await service.create_api_key(connector.id)

        keys = await service.list_api_keys(connector.id)
        assert len(keys) == 2
        for key in keys:
            assert key.enabled is True

    async def test_delete_api_key(self, company_factory):
        service = ConnectorsService()
        company = await company_factory()
        connector = await Connector.create(
            connector_id="delete-key-test",
            company=company,
            type=ConnectorType.CUSTOM,
            channel_type="custom",
            display_name="Delete Key Test",
            managed=False,
            config={},
        )
        key_response = await service.create_api_key(connector.id)

        await service.delete_api_key(key_response.id)
        keys = await service.list_api_keys(connector.id)
        assert len(keys) == 0

    async def test_delete_api_key_not_found(self):
        service = ConnectorsService()
        with pytest.raises(ConnectorNotFoundError):
            await service.delete_api_key(99999)

    async def test_disable_api_key(self, company_factory):
        service = ConnectorsService()
        company = await company_factory()
        connector = await Connector.create(
            connector_id="disable-key-test",
            company=company,
            type=ConnectorType.CUSTOM,
            channel_type="custom",
            display_name="Disable Key Test",
            managed=False,
            config={},
        )
        key_response = await service.create_api_key(connector.id)

        await service.disable_api_key(key_response.id)
        keys = await service.list_api_keys(connector.id)
        assert len(keys) == 1
        assert keys[0].enabled is False


class TestConnectorsServicePromptAddon:
    async def test_update_connector_prompt_addon_success(self, company_factory):
        from src.backend.modules.prompt_addon.models import PromptAddon

        service = ConnectorsService()
        company = await company_factory()
        addon = await PromptAddon.create(
            company=company,
            name="Test Addon",
            qualification_workflow="Test workflow",
            qualification_examples="Test examples",
        )
        connector = await Connector.create(
            connector_id="test-connector",
            company=company,
            type=ConnectorType.TELEGRAM,
            channel_type="telegram",
            display_name="Test Bot",
            managed=True,
            config={"bot_token": "token"},
        )
        result = await service.update_connector_prompt_addon(
            company_id=company.id,
            connector_id=connector.connector_id,
            prompt_addon_id=addon.id,
        )
        assert result.prompt_addon_id == addon.id

        refreshed = await Connector.get(id=connector.id)
        assert refreshed.prompt_addon_id == addon.id

    async def test_update_connector_prompt_addon_remove(self, company_factory):
        from src.backend.modules.prompt_addon.models import PromptAddon

        service = ConnectorsService()
        company = await company_factory()
        addon = await PromptAddon.create(
            company=company,
            name="Test Addon",
            qualification_workflow="Workflow",
            qualification_examples="Examples",
        )
        connector = await Connector.create(
            connector_id="test-connector-2",
            company=company,
            type=ConnectorType.TELEGRAM,
            channel_type="telegram",
            display_name="Test Bot",
            managed=True,
            config={"bot_token": "token"},
            prompt_addon_id=addon.id,
        )
        result = await service.update_connector_prompt_addon(
            company_id=company.id,
            connector_id=connector.connector_id,
            prompt_addon_id=None,
        )
        assert result.prompt_addon_id is None

        refreshed = await Connector.get(id=connector.id)
        assert refreshed.prompt_addon_id is None

    async def test_update_connector_prompt_addon_connector_not_found(self, company_factory):
        from src.backend.modules.prompt_addon.models import PromptAddon

        service = ConnectorsService()
        company = await company_factory()
        addon = await PromptAddon.create(
            company=company,
            name="Test Addon",
            qualification_workflow="Workflow",
            qualification_examples="Examples",
        )
        with pytest.raises(ConnectorNotFoundError):
            await service.update_connector_prompt_addon(
                company_id=company.id,
                connector_id="non-existent",
                prompt_addon_id=addon.id,
            )

    async def test_update_connector_prompt_addon_wrong_company(self, company_factory):
        service = ConnectorsService()
        company1 = await company_factory()
        company2 = await company_factory()
        connector = await Connector.create(
            connector_id="test-connector-3",
            company=company1,
            type=ConnectorType.TELEGRAM,
            channel_type="telegram",
            display_name="Test Bot",
            managed=True,
            config={"bot_token": "token"},
        )
        with pytest.raises(ConnectorNotFoundError):
            await service.update_connector_prompt_addon(
                company_id=company2.id,
                connector_id=connector.connector_id,
                prompt_addon_id=None,
            )

    async def test_update_connector_prompt_addon_addon_not_found(self, company_factory):
        service = ConnectorsService()
        company = await company_factory()
        connector = await Connector.create(
            connector_id="test-connector-4",
            company=company,
            type=ConnectorType.TELEGRAM,
            channel_type="telegram",
            display_name="Test Bot",
            managed=True,
            config={"bot_token": "token"},
        )
        from src.backend.modules.prompt_addon.exceptions import PromptAddonNotFoundError

        with pytest.raises(PromptAddonNotFoundError):
            await service.update_connector_prompt_addon(
                company_id=company.id,
                connector_id=connector.connector_id,
                prompt_addon_id=99999,
            )

    async def test_update_connector_prompt_addon_wrong_company_addon(self, company_factory):
        from src.backend.modules.prompt_addon.models import PromptAddon

        service = ConnectorsService()
        company1 = await company_factory()
        company2 = await company_factory()
        addon = await PromptAddon.create(
            company=company2,
            name="Other Company Addon",
            qualification_workflow="Workflow",
            qualification_examples="Examples",
        )
        connector = await Connector.create(
            connector_id="test-connector-5",
            company=company1,
            type=ConnectorType.TELEGRAM,
            channel_type="telegram",
            display_name="Test Bot",
            managed=True,
            config={"bot_token": "token"},
        )
        from src.backend.modules.prompt_addon.exceptions import PromptAddonNotFoundError

        with pytest.raises(PromptAddonNotFoundError):
            await service.update_connector_prompt_addon(
                company_id=company1.id,
                connector_id=connector.connector_id,
                prompt_addon_id=addon.id,
            )


class TestDecryptionErrorHandling:
    async def test_decrypt_config_invalid_payload_raises(self):
        service = ConnectorsService()
        bad_config = {"bot_token": {"not": "an_encrypted_payload"}}
        with pytest.raises(RuntimeError, match="Decryption failed for field 'bot_token'"):
            service._decrypt_config(ConnectorType.TELEGRAM, bad_config)

    async def test_decrypt_config_non_dict_field_skipped(self):
        service = ConnectorsService()
        config = {"bot_token": "plaintext", "mode": "auto"}
        result = service._decrypt_config(ConnectorType.TELEGRAM, config)
        assert result == config

    async def test_list_connectors_decrypted_skips_corrupted_connector(self, company_factory):
        service = ConnectorsService()
        company = await company_factory()

        await Connector.create(
            connector_id="good-connector",
            company=company,
            type=ConnectorType.TELEGRAM,
            channel_type="telegram",
            display_name="Good Bot",
            managed=True,
            config=service._encrypt_config(ConnectorType.TELEGRAM, {"bot_token": "real-token"}),
            enabled=True,
        )
        await Connector.create(
            connector_id="bad-connector",
            company=company,
            type=ConnectorType.TELEGRAM,
            channel_type="telegram",
            display_name="Bad Bot",
            managed=True,
            config={"bot_token": {"corrupted": "garbage"}},
            enabled=True,
        )

        result = await service.list_connectors_decrypted()
        connector_ids = [r.connector_id for r in result]
        assert "good-connector" in connector_ids
        assert "bad-connector" not in connector_ids
