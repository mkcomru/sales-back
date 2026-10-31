from typing import Any

from tortoise.exceptions import DoesNotExist

from src.backend.modules.core.base_repo import BaseRepository
from src.backend.modules.transport.models import Connector, ConnectorApiKey, ConnectorType


class ConnectorsRepository(BaseRepository[Connector]):
    """Repository for unified Connector model."""

    def __init__(self) -> None:
        super().__init__(Connector)

    async def list_all(self) -> list[Connector]:
        return await self.model.all().prefetch_related("company").order_by("connector_id")

    async def list_filtered(
        self,
        type_filter: str | None = None,
        enabled_filter: bool | None = None,
    ) -> list[Connector]:
        queryset = self.model.all()
        if type_filter:
            queryset = queryset.filter(type=type_filter)
        if enabled_filter is not None:
            queryset = queryset.filter(enabled=enabled_filter)
        return await queryset.prefetch_related("company").order_by("connector_id")

    async def list_enabled(self) -> list[Connector]:
        return await self.model.filter(enabled=True).prefetch_related("company").order_by("connector_id")

    async def list_by_company(self, company_id: int) -> list[Connector]:
        return await self.model.filter(company_id=company_id).prefetch_related("company").order_by("connector_id")

    async def list_by_company_paginated(self, company_id: int, limit: int, offset: int) -> tuple[list[Connector], int]:
        total = await self.model.filter(company_id=company_id).count()
        items = (
            await self.model.filter(company_id=company_id)
            .prefetch_related("company")
            .order_by("connector_id")
            .offset(offset)
            .limit(limit)
        )
        return items, total

    async def get_by_id(self, connector_db_id: int) -> Connector | None:
        try:
            return await self.model.get(id=connector_db_id).prefetch_related("company")
        except DoesNotExist:
            return None

    async def get_by_connector_id(self, connector_id: str) -> Connector | None:
        try:
            return await self.model.get(connector_id=connector_id).prefetch_related("company")
        except DoesNotExist:
            return None

    async def create_connector(
        self,
        *,
        connector_id: str,
        company_id: int,
        connector_type: ConnectorType,
        channel_type: str,
        display_name: str,
        managed: bool,
        config: dict[str, Any],
        enabled: bool,
        debounce_window_seconds: int,
        debounce_storage_key_template: str,
    ) -> Connector:
        return await self._create(
            connector_id=connector_id,
            company_id=company_id,
            type=connector_type,
            channel_type=channel_type,
            display_name=display_name,
            managed=managed,
            config=config,
            enabled=enabled,
            debounce_window_seconds=debounce_window_seconds,
            debounce_storage_key_template=debounce_storage_key_template,
        )

    async def update_connector(
        self,
        connector_db_id: int,
        updates: dict[str, Any],
    ) -> Connector | None:
        return await self._update(id=connector_db_id, updates=updates)

    async def delete_connector(self, connector_db_id: int) -> bool:
        return await self._delete(id=connector_db_id)


class ConnectorApiKeysRepository(BaseRepository[ConnectorApiKey]):
    """Repository for ConnectorApiKey model."""

    def __init__(self) -> None:
        super().__init__(ConnectorApiKey)

    async def get_by_hash(self, key_hash: str) -> ConnectorApiKey | None:
        try:
            return await self.model.get(key_hash=key_hash).prefetch_related("connector", "connector__company")
        except DoesNotExist:
            return None

    async def get_enabled_by_hash(self, key_hash: str) -> ConnectorApiKey | None:
        try:
            return await self.model.get(key_hash=key_hash, enabled=True).prefetch_related(
                "connector", "connector__company"
            )
        except DoesNotExist:
            return None

    async def list_by_connector(self, connector_id: int) -> list[ConnectorApiKey]:
        return await self.model.filter(connector_id=connector_id).order_by("-created_at")

    async def create_key(
        self,
        *,
        key_hash: str,
        connector_id: int,
        enabled: bool = True,
    ) -> ConnectorApiKey:
        return await self._create(
            key_hash=key_hash,
            connector_id=connector_id,
            enabled=enabled,
        )

    async def disable_key(self, key_id: int) -> ConnectorApiKey | None:
        return await self._update(id=key_id, updates={"enabled": False})

    async def delete_key(self, key_id: int) -> bool:
        return await self._delete(id=key_id)
