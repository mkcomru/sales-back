"""Shared common utilities for sales monorepo."""

from common.clients import SalesAgentInboundClient
from common.connectors import ConnectorCapability, ConnectorTypeCatalogEntry
from common.logging_setup import log, setup_logging
from common.models import AudioData, ConnectorContext, DebounceConfig, InboundEnvelope, MessageRole
from common.models.transport import AttachmentDescriptor, TransportDeliveryPayload
from common.schemas import FileType
from common.services import ArtifactService, AudioConversionService
from common.transport import (
    CONNECTOR_TYPE_CATALOG,
    BaseConnectorConfig,
    BaseConnectorManager,
    BaseTransportBackendClient,
    BaseTransportDeliveryService,
    ConnectorModuleError,
    TransportBackendClientError,
    register_connector_type,
    validate_connector_module,
)
from common.utils.retry import RetryStrategy, retry_with_backoff

from .config import (
    BackendModuleSettings,
    S3Settings,
    SalesAgentSettings,
    ServiceAuthSettings,
    TelegramModuleSettings,
    WappiModuleSettings,
    WazzupModuleSettings,
)
from .tools import TOOL_CATALOG, AvailableTool, ToolGroup

__all__ = [
    "AvailableTool",
    "TOOL_CATALOG",
    "ToolGroup",
    "BackendModuleSettings",
    "SalesAgentSettings",
    "TelegramModuleSettings",
    "WappiModuleSettings",
    "WazzupModuleSettings",
    "ServiceAuthSettings",
    "S3Settings",
    "log",
    "setup_logging",
    # Inbound envelope schemas
    "AudioData",
    "ConnectorContext",
    "DebounceConfig",
    "InboundEnvelope",
    "MessageRole",
    # Transport payload
    "AttachmentDescriptor",
    "TransportDeliveryPayload",
    # Connector capabilities & catalog
    "ConnectorCapability",
    "ConnectorTypeCatalogEntry",
    "CONNECTOR_TYPE_CATALOG",
    "register_connector_type",
    # Transport ABCs
    "BaseConnectorConfig",
    "BaseConnectorManager",
    "BaseTransportBackendClient",
    "BaseTransportDeliveryService",
    "TransportBackendClientError",
    # Runtime validation
    "ConnectorModuleError",
    "validate_connector_module",
    # Clients
    "SalesAgentInboundClient",
    # Services
    "ArtifactService",
    "AudioConversionService",
    # Schemas
    "FileType",
    # Utils
    "RetryStrategy",
    "retry_with_backoff",
]
