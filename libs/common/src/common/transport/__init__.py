"""Transport contracts — base classes and registry for connector modules."""

from common.transport.base_backend_client import BaseTransportBackendClient, TransportBackendClientError
from common.transport.base_config import BaseConnectorConfig
from common.transport.base_delivery import BaseTransportDeliveryService
from common.transport.base_manager import BaseConnectorManager
from common.transport.registry import CONNECTOR_TYPE_CATALOG, register_connector_type, resolve_catalog_key
from common.transport.validation import ConnectorModuleError, validate_connector_module

__all__ = [
    "BaseConnectorConfig",
    "BaseConnectorManager",
    "BaseTransportBackendClient",
    "BaseTransportDeliveryService",
    "ConnectorModuleError",
    "CONNECTOR_TYPE_CATALOG",
    "TransportBackendClientError",
    "register_connector_type",
    "resolve_catalog_key",
    "validate_connector_module",
]
