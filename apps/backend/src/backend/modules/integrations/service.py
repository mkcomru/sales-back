from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import structlog

from common.crypto import EncryptedPayload, EnvelopeEncryption
from common.integrations import Capability

from src.backend.integrations.base import BaseIntegrationClient
from src.backend.modules.core.settings import get_settings
from src.backend.modules.integrations.exceptions import (
    IntegrationCapabilityConflictError,
    IntegrationNotFoundError,
)
from src.backend.modules.integrations.models import Integration
from src.backend.modules.integrations.repository import IntegrationRepository

log = structlog.get_logger(__name__)


class IntegrationService:
    def __init__(self, repo: IntegrationRepository | None = None) -> None:
        self._repo = repo or IntegrationRepository()

    def _get_encryption(self) -> EnvelopeEncryption:
        settings = get_settings()
        master_key = settings.encryption.master_key
        if not master_key:
            raise RuntimeError("ENCRYPTION__MASTER_KEY is not configured")
        return EnvelopeEncryption(master_key.get_secret_value())

    def _encrypt_credentials(self, credentials: dict[str, Any]) -> tuple[str, str]:
        enc = self._get_encryption()
        payload = enc.encrypt(json.dumps(credentials).encode())
        return payload.encrypted_data, payload.encrypted_dek

    def _decrypt_credentials(self, integration: Integration) -> dict[str, Any]:
        if not integration.credentials_encrypted or not integration.credentials_dek:
            return {}
        enc = self._get_encryption()
        payload = EncryptedPayload(
            encrypted_data=integration.credentials_encrypted,
            encrypted_dek=integration.credentials_dek,
        )
        return json.loads(enc.decrypt(payload))

    async def _check_capability_conflicts(
        self,
        company_id: int,
        new_capabilities: list[str],
        exclude_id: int | None = None,
    ) -> None:
        existing = await self._repo.get_for_company(company_id)
        for other in existing:
            if other.id == exclude_id:
                continue
            overlap = set(new_capabilities) & set(other.enabled_capabilities)
            if overlap:
                raise IntegrationCapabilityConflictError(
                    f"Capabilities {overlap} already provided by {other.provider_type}"
                )

    async def create(
        self,
        company_id: int,
        provider_type: str,
        credentials: dict[str, Any],
        config: dict[str, Any],
        enabled_capabilities: list[str],
        enabled: bool = True,
    ) -> Integration:
        await self._check_capability_conflicts(company_id, enabled_capabilities)
        enc_data, enc_dek = self._encrypt_credentials(credentials)
        integration = await Integration.create(
            company_id=company_id,
            provider_type=provider_type,
            credentials_encrypted=enc_data,
            credentials_dek=enc_dek,
            config=config,
            enabled_capabilities=enabled_capabilities,
            enabled=enabled,
        )
        log.info(
            "integration.created",
            integration_id=integration.id,
            company_id=company_id,
            provider_type=provider_type,
            capabilities=enabled_capabilities,
        )
        return integration

    async def update(
        self,
        integration_id: int,
        *,
        credentials: dict[str, Any] | None = None,
        config: dict[str, Any] | None = None,
        enabled_capabilities: list[str] | None = None,
        enabled: bool | None = None,
    ) -> Integration:
        integration = await self._repo.get_by_id(integration_id)
        if not integration:
            raise IntegrationNotFoundError(f"Integration {integration_id} not found")

        if enabled_capabilities is not None:
            await self._check_capability_conflicts(
                integration.company_id, enabled_capabilities, exclude_id=integration.id
            )
            integration.enabled_capabilities = enabled_capabilities

        if credentials is not None:
            enc_data, enc_dek = self._encrypt_credentials(credentials)
            integration.credentials_encrypted = enc_data
            integration.credentials_dek = enc_dek

        if config is not None:
            integration.config = config

        if enabled is not None:
            integration.enabled = enabled

        await integration.save()
        log.info("integration.updated", integration_id=integration.id)
        return integration

    async def delete(self, integration_id: int) -> None:
        integration = await self._repo.get_by_id(integration_id)
        if not integration:
            raise IntegrationNotFoundError(f"Integration {integration_id} not found")
        await integration.delete()
        log.info("integration.deleted", integration_id=integration_id)

    async def list_for_company(self, company_id: int) -> list[Integration]:
        return await Integration.filter(company_id=company_id)

    async def get(self, integration_id: int) -> Integration:
        integration = await self._repo.get_by_id(integration_id)
        if not integration:
            raise IntegrationNotFoundError(f"Integration {integration_id} not found")
        return integration

    def decrypt_credentials(self, integration: Integration) -> dict[str, Any]:
        return self._decrypt_credentials(integration)

    async def resolve_by_capability(self, company_id: int, capability: Capability) -> Integration:
        integration = await self._repo.get_by_capability(company_id, capability)
        if not integration:
            raise IntegrationNotFoundError(f"No {capability.value} provider configured for company {company_id}")
        return integration

    @asynccontextmanager
    async def build_client(self, integration: Integration) -> AsyncIterator[BaseIntegrationClient]:
        """Build and yield a provider-specific client as an async context manager.

        Returns BaseIntegrationClient statically. Callers narrow to the
        concrete type via ``assert isinstance(client, YClientsClient)``
        for full type safety without leaking the type into this method.
        """
        from src.backend.modules.integrations.registry import CLIENT_BUILDERS

        builder = CLIENT_BUILDERS.get(integration.provider_type)
        if not builder:
            raise RuntimeError(f"No client builder registered for provider '{integration.provider_type}'")
        credentials = self.decrypt_credentials(integration)
        client = builder(credentials, integration.config)
        async with client:
            yield client
