from __future__ import annotations

from abc import ABC, abstractmethod


class BaseConnectorManager[TConfig](ABC):
    """Contract for connector lifecycle managers in transport modules."""

    @abstractmethod
    async def reload(self) -> None:
        """Reload connector configurations from backend service."""
        ...

    @abstractmethod
    def get(self, connector_id: str) -> TConfig | None:
        """Return connector config by id, or None if not loaded."""
        ...

    @abstractmethod
    async def shutdown(self) -> None:
        """Gracefully shut down all managed connectors."""
        ...
