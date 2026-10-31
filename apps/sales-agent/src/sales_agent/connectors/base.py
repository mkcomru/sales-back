from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any

from src.sales_agent.services.debounce import IncomingMessage


class ConnectorError(Exception):
    """Base error for connector processing issues."""


class ConnectorAuthError(ConnectorError):
    """Raised when inbound authentication fails."""


class ConnectorPayloadError(ConnectorError):
    """Raised when inbound payload cannot be normalized."""


class ConnectorType(str, Enum):
    """High-level category of connector responsibilities."""

    CRM = "crm"
    MESSAGING = "messaging"


class ConnectorCapability(str, Enum):
    """Granular actions a connector is expected to provide."""

    DELIVER_MESSAGES = "deliver_messages"
    COMMIT_HANDOFF = "commit_handoff"
    SYNC_STAGE = "sync_stage"


CONNECTOR_MIN_CAPABILITIES: dict[ConnectorType, frozenset[ConnectorCapability]] = {
    ConnectorType.CRM: frozenset(
        {
            ConnectorCapability.DELIVER_MESSAGES,
            ConnectorCapability.COMMIT_HANDOFF,
            ConnectorCapability.SYNC_STAGE,
        }
    ),
    ConnectorType.MESSAGING: frozenset(
        {
            ConnectorCapability.DELIVER_MESSAGES,
        }
    ),
}


@dataclass(slots=True, frozen=True)
class InboundPayload:
    """Raw HTTP payload data passed into an inbound connector."""

    body: Mapping[str, Any]
    headers: Mapping[str, str] | None = None
    query_params: Mapping[str, str] | None = None
    metadata: Mapping[str, Any] | None = None


@dataclass(slots=True, frozen=True)
class ConnectorContext:
    """Resolved connector metadata for downstream processing."""

    connector_id: str
    connector_type: ConnectorType
    channel_type: str | None = None
    capabilities: frozenset[ConnectorCapability] = frozenset()
    config_snapshot: Mapping[str, Any] | None = None


class InboundConnector(ABC):
    """Normalizes vendor-specific events into `IncomingMessage` batches."""

    @property
    @abstractmethod
    def connector_id(self) -> str: ...

    @property
    @abstractmethod
    def connector_type(self) -> ConnectorType: ...

    @abstractmethod
    async def normalize(
        self,
        payload: InboundPayload,
    ) -> Sequence[IncomingMessage]: ...
