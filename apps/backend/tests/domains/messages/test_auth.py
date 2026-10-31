"""Tests for message routing authentication helpers."""

import pytest

from src.backend.modules.messages.auth import get_managed_connector, validate_bearer_token
from src.backend.modules.transport.models import Connector, ConnectorApiKey, ConnectorType
from src.backend.modules.transport.service import ConnectorsService


class TestValidateBearerToken:
    """Tests for validate_bearer_token function."""

    async def test_validate_bearer_token_success(self, company_factory):
        """Test successful Bearer token validation."""
        company = await company_factory()
        connector = await Connector.create(
            connector_id="custom-connector",
            company=company,
            type=ConnectorType.CUSTOM,
            channel_type="custom-channel",
            display_name="Custom Connector",
            managed=False,
            config={},
            enabled=True,
        )

        # Create API key
        raw_key = "sk_test_key_123"  # pragma: allowlist secret
        import hashlib

        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        await ConnectorApiKey.create(
            connector=connector,
            key_hash=key_hash,
            display_name="Test Key",
        )

        service = ConnectorsService()
        context = await validate_bearer_token(service, f"Bearer {raw_key}")

        assert context.connector_id == "custom-connector"
        assert context.company_id == company.id

    async def test_validate_bearer_token_malformed_no_bearer(self):
        """Test Bearer token validation with malformed header (no Bearer prefix)."""
        from fastapi import HTTPException

        service = ConnectorsService()
        with pytest.raises(HTTPException):
            await validate_bearer_token(service, "sk_test_key_123")  # pragma: allowlist secret

    async def test_validate_bearer_token_malformed_empty_token(self):
        """Test Bearer token validation with empty token."""
        from fastapi import HTTPException

        service = ConnectorsService()
        with pytest.raises(HTTPException):
            await validate_bearer_token(service, "Bearer ")

    async def test_validate_bearer_token_invalid_key(self):
        """Test Bearer token validation with invalid key."""
        from fastapi import HTTPException

        service = ConnectorsService()
        with pytest.raises(HTTPException):
            await validate_bearer_token(service, "Bearer invalid_key_123")


class TestGetManagedConnector:
    """Tests for get_managed_connector function."""

    async def test_get_managed_connector_success(self, company_factory):
        """Test successful managed connector lookup."""
        company = await company_factory()
        await Connector.create(
            connector_id="tg-managed",
            company=company,
            type=ConnectorType.TELEGRAM,
            channel_type="telegram",
            display_name="Managed Bot",
            managed=True,
            config={"bot_token": "token123"},
            enabled=True,
        )

        service = ConnectorsService()
        context = await get_managed_connector(service, "tg-managed")

        assert context.connector_id == "tg-managed"
        assert context.company_id == company.id

    async def test_get_managed_connector_disabled(self, company_factory):
        """Test managed connector lookup for disabled connector."""
        from fastapi import HTTPException

        company = await company_factory()
        await Connector.create(
            connector_id="tg-disabled",
            company=company,
            type=ConnectorType.TELEGRAM,
            channel_type="telegram",
            display_name="Disabled Bot",
            managed=True,
            config={"bot_token": "token123"},
            enabled=False,  # Disabled
        )

        service = ConnectorsService()
        with pytest.raises(HTTPException):
            await get_managed_connector(service, "tg-disabled")

    async def test_get_managed_connector_not_found(self):
        """Test managed connector lookup for non-existent connector."""
        from fastapi import HTTPException

        service = ConnectorsService()
        with pytest.raises(HTTPException):
            await get_managed_connector(service, "nonexistent-bot")
