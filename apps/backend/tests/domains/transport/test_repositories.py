"""Repository tests for unified Connector model."""

import hashlib

from src.backend.modules.transport.models import Connector, ConnectorApiKey, ConnectorType
from src.backend.modules.transport.repository import ConnectorApiKeysRepository, ConnectorsRepository


class TestConnectorsRepository:
    async def test_list_all_empty(self):
        repo = ConnectorsRepository()
        result = await repo.list_all()
        assert result == []

    async def test_list_all_with_data(self, company_factory):
        repo = ConnectorsRepository()
        company = await company_factory()
        await Connector.create(
            connector_id="repo-test-1",
            company=company,
            type=ConnectorType.TELEGRAM,
            channel_type="telegram",
            display_name="Repo Test",
            managed=True,
            config={"bot_token": "tok"},
        )
        result = await repo.list_all()
        assert len(result) == 1
        assert result[0].connector_id == "repo-test-1"

    async def test_list_enabled(self, company_factory):
        repo = ConnectorsRepository()
        company = await company_factory()
        await Connector.create(
            connector_id="enabled-1",
            company=company,
            type=ConnectorType.TELEGRAM,
            channel_type="telegram",
            display_name="Enabled",
            managed=True,
            config={"bot_token": "tok"},
            enabled=True,
        )
        await Connector.create(
            connector_id="disabled-1",
            company=company,
            type=ConnectorType.TELEGRAM,
            channel_type="telegram",
            display_name="Disabled",
            managed=True,
            config={"bot_token": "tok"},
            enabled=False,
        )
        result = await repo.list_enabled()
        assert len(result) == 1
        assert result[0].connector_id == "enabled-1"

    async def test_list_by_company(self, company_factory):
        repo = ConnectorsRepository()
        company1 = await company_factory()
        company2 = await company_factory()
        await Connector.create(
            connector_id="c1-connector",
            company=company1,
            type=ConnectorType.TELEGRAM,
            channel_type="telegram",
            display_name="C1",
            managed=True,
            config={"bot_token": "tok"},
        )
        await Connector.create(
            connector_id="c2-connector",
            company=company2,
            type=ConnectorType.TELEGRAM,
            channel_type="telegram",
            display_name="C2",
            managed=True,
            config={"bot_token": "tok"},
        )
        result = await repo.list_by_company(company1.id)
        assert len(result) == 1
        assert result[0].connector_id == "c1-connector"

    async def test_list_by_company_paginated(self, company_factory):
        repo = ConnectorsRepository()
        company = await company_factory()
        for i in range(5):
            await Connector.create(
                connector_id=f"page-conn-{i}",
                company=company,
                type=ConnectorType.TELEGRAM,
                channel_type="telegram",
                display_name=f"Page {i}",
                managed=True,
                config={"bot_token": "tok"},
            )
        items, total = await repo.list_by_company_paginated(company.id, limit=2, offset=0)
        assert len(items) == 2
        assert total == 5

    async def test_get_by_id(self, company_factory):
        repo = ConnectorsRepository()
        company = await company_factory()
        connector = await Connector.create(
            connector_id="get-by-id",
            company=company,
            type=ConnectorType.TELEGRAM,
            channel_type="telegram",
            display_name="Get By ID",
            managed=True,
            config={"bot_token": "tok"},
        )
        result = await repo.get_by_id(connector.id)
        assert result is not None
        assert result.connector_id == "get-by-id"

    async def test_get_by_id_not_found(self):
        repo = ConnectorsRepository()
        result = await repo.get_by_id(99999)
        assert result is None

    async def test_get_by_connector_id(self, company_factory):
        repo = ConnectorsRepository()
        company = await company_factory()
        await Connector.create(
            connector_id="public-id",
            company=company,
            type=ConnectorType.TELEGRAM,
            channel_type="telegram",
            display_name="Public ID",
            managed=True,
            config={"bot_token": "tok"},
        )
        result = await repo.get_by_connector_id("public-id")
        assert result is not None
        assert result.connector_id == "public-id"

    async def test_get_by_connector_id_not_found(self):
        repo = ConnectorsRepository()
        result = await repo.get_by_connector_id("non-existent")
        assert result is None

    async def test_create_connector(self, company_factory):
        repo = ConnectorsRepository()
        company = await company_factory()
        connector = await repo.create_connector(
            connector_id="created-conn",
            company_id=company.id,
            connector_type=ConnectorType.WAPPI,
            channel_type="whatsapp",
            display_name="Created Connector",
            managed=True,
            config={"wappi_token": "tok", "wappi_profile_id": "prof", "transport_endpoint": "https://x.com"},
            enabled=True,
            debounce_window_seconds=45,
            debounce_storage_key_template="{connector_id}:{conversation_id}",
        )
        assert connector.connector_id == "created-conn"
        assert connector.type == ConnectorType.WAPPI

    async def test_update_connector(self, company_factory):
        repo = ConnectorsRepository()
        company = await company_factory()
        connector = await Connector.create(
            connector_id="update-repo",
            company=company,
            type=ConnectorType.TELEGRAM,
            channel_type="telegram",
            display_name="Original",
            managed=True,
            config={"bot_token": "tok"},
        )
        updated = await repo.update_connector(connector.id, {"display_name": "Updated", "enabled": False})
        assert updated is not None
        assert updated.display_name == "Updated"
        assert updated.enabled is False

    async def test_update_connector_not_found(self):
        repo = ConnectorsRepository()
        result = await repo.update_connector(99999, {"display_name": "X"})
        assert result is None

    async def test_delete_connector(self, company_factory):
        repo = ConnectorsRepository()
        company = await company_factory()
        connector = await Connector.create(
            connector_id="delete-repo",
            company=company,
            type=ConnectorType.TELEGRAM,
            channel_type="telegram",
            display_name="Delete Me",
            managed=True,
            config={"bot_token": "tok"},
        )
        result = await repo.delete_connector(connector.id)
        assert result is True
        found = await Connector.get_or_none(id=connector.id)
        assert found is None

    async def test_delete_connector_not_found(self):
        repo = ConnectorsRepository()
        result = await repo.delete_connector(99999)
        assert result is False


class TestConnectorApiKeysRepository:
    async def test_get_by_hash(self, company_factory):
        repo = ConnectorApiKeysRepository()
        company = await company_factory()
        connector = await Connector.create(
            connector_id="key-hash-test",
            company=company,
            type=ConnectorType.CUSTOM,
            channel_type="custom",
            display_name="Key Hash",
            managed=False,
            config={},
        )
        key_hash = hashlib.sha256(b"sk_test_key").hexdigest()
        await ConnectorApiKey.create(key_hash=key_hash, connector=connector, enabled=True)

        result = await repo.get_by_hash(key_hash)
        assert result is not None
        assert result.key_hash == key_hash

    async def test_get_by_hash_not_found(self):
        repo = ConnectorApiKeysRepository()
        result = await repo.get_by_hash("nonexistent_hash")
        assert result is None

    async def test_get_enabled_by_hash(self, company_factory):
        repo = ConnectorApiKeysRepository()
        company = await company_factory()
        connector = await Connector.create(
            connector_id="enabled-key-test",
            company=company,
            type=ConnectorType.CUSTOM,
            channel_type="custom",
            display_name="Enabled Key",
            managed=False,
            config={},
        )
        enabled_hash = hashlib.sha256(b"sk_enabled").hexdigest()
        disabled_hash = hashlib.sha256(b"sk_disabled").hexdigest()
        await ConnectorApiKey.create(key_hash=enabled_hash, connector=connector, enabled=True)
        await ConnectorApiKey.create(key_hash=disabled_hash, connector=connector, enabled=False)

        enabled_result = await repo.get_enabled_by_hash(enabled_hash)
        assert enabled_result is not None

        disabled_result = await repo.get_enabled_by_hash(disabled_hash)
        assert disabled_result is None

    async def test_list_by_connector(self, company_factory):
        repo = ConnectorApiKeysRepository()
        company = await company_factory()
        connector = await Connector.create(
            connector_id="list-keys-repo",
            company=company,
            type=ConnectorType.CUSTOM,
            channel_type="custom",
            display_name="List Keys",
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
        result = await repo.list_by_connector(connector.id)
        assert len(result) == 2

    async def test_create_key(self, company_factory):
        repo = ConnectorApiKeysRepository()
        company = await company_factory()
        connector = await Connector.create(
            connector_id="create-key-repo",
            company=company,
            type=ConnectorType.CUSTOM,
            channel_type="custom",
            display_name="Create Key",
            managed=False,
            config={},
        )
        key_hash = hashlib.sha256(b"sk_new_key").hexdigest()
        key = await repo.create_key(key_hash=key_hash, connector_id=connector.id, enabled=True)
        assert key.key_hash == key_hash
        assert key.enabled is True

    async def test_disable_key(self, company_factory):
        repo = ConnectorApiKeysRepository()
        company = await company_factory()
        connector = await Connector.create(
            connector_id="disable-key-repo",
            company=company,
            type=ConnectorType.CUSTOM,
            channel_type="custom",
            display_name="Disable Key",
            managed=False,
            config={},
        )
        key = await ConnectorApiKey.create(
            key_hash=hashlib.sha256(b"sk_to_disable").hexdigest(),
            connector=connector,
            enabled=True,
        )
        result = await repo.disable_key(key.id)
        assert result is not None
        assert result.enabled is False

    async def test_delete_key(self, company_factory):
        repo = ConnectorApiKeysRepository()
        company = await company_factory()
        connector = await Connector.create(
            connector_id="delete-key-repo",
            company=company,
            type=ConnectorType.CUSTOM,
            channel_type="custom",
            display_name="Delete Key",
            managed=False,
            config={},
        )
        key = await ConnectorApiKey.create(
            key_hash=hashlib.sha256(b"sk_to_delete").hexdigest(),
            connector=connector,
            enabled=True,
        )
        result = await repo.delete_key(key.id)
        assert result is True
        found = await ConnectorApiKey.get_or_none(id=key.id)
        assert found is None
