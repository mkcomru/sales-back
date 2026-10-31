from __future__ import annotations

from collections.abc import Iterable

from common.connectors import ConnectorCapability, ConnectorTypeCatalogEntry
from common.sync.base import BaseSyncProvider
from common.transport.base_delivery import BaseTransportDeliveryService


class ConnectorModuleError(RuntimeError):
    """Raised when a transport module's declared capabilities contradict its implementation."""


def validate_connector_module(
    entries: ConnectorTypeCatalogEntry | Iterable[ConnectorTypeCatalogEntry],
    delivery_service: BaseTransportDeliveryService,
    sync_provider: BaseSyncProvider | type[BaseSyncProvider] | None = None,
) -> None:
    """Validate that declared capabilities are backed by actual implementations.

    Call during app lifespan startup to catch deploy-time mismatches before
    users trigger them at runtime.

    ``entries`` can be a single entry or multiple (hub-style transports like wappi
    serve multiple catalog variants from one module).

    ``sync_provider`` can be an instance OR the class itself — connectors that
    create providers per-job (e.g. wappi) pass the class; connectors with
    a persistent provider pass the instance.

    Raises:
        ConnectorModuleError: If a declared capability has no implementation.
    """
    if not isinstance(delivery_service, BaseTransportDeliveryService):
        raise ConnectorModuleError(
            f"delivery_service must be a BaseTransportDeliveryService instance, got {type(delivery_service).__name__}"
        )

    entry_list = [entries] if isinstance(entries, ConnectorTypeCatalogEntry) else list(entries)

    for entry in entry_list:
        if ConnectorCapability.HISTORY_SYNC in entry.supported_capabilities and sync_provider is None:
            raise ConnectorModuleError(
                f"Connector '{entry.connector_type}' declared {ConnectorCapability.HISTORY_SYNC} "
                "but no BaseSyncProvider was provided"
            )

    if sync_provider is not None:
        is_instance = isinstance(sync_provider, BaseSyncProvider)
        is_subclass = isinstance(sync_provider, type) and issubclass(sync_provider, BaseSyncProvider)
        if not is_instance and not is_subclass:
            raise ConnectorModuleError(
                f"sync_provider must be a BaseSyncProvider instance or subclass, got {sync_provider!r}"
            )
