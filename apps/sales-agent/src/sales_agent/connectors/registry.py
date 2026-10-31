from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from fastapi import APIRouter

from src.sales_agent.connectors.base import InboundConnector

if TYPE_CHECKING:
    from src.sales_agent.core.telemetry import Tracer


class ConnectorRegistry:
    """Runtime registry for inbound connector instances and HTTP routers."""

    def __init__(self, tracer: Tracer | None = None) -> None:
        self._inbound: dict[str, InboundConnector] = {}
        self._routers: dict[str, APIRouter] = {}
        self._tracer = tracer

    def register_inbound(self, connector: InboundConnector, router: APIRouter) -> None:
        connector_id = connector.connector_id
        self._inbound[connector_id] = connector
        self._routers[connector_id] = router
        if self._tracer:
            tags = self._tracer.connector_tags(
                connector_id=connector_id,
                connector_type=connector.connector_type.value,
                extra=["connector", "inbound"],
            )
            self._tracer.record_event(
                "connector.registered",
                metadata={
                    "connector_id": connector_id,
                    "connector_type": connector.connector_type.value,
                    "direction": "inbound",
                },
                tags=tags,
            )

    def get_inbound(self, connector_id: str) -> InboundConnector | None:
        return self._inbound.get(connector_id)

    def require_inbound(self, connector_id: str) -> InboundConnector:
        connector = self.get_inbound(connector_id)
        if connector is None:
            raise LookupError(f"Inbound connector '{connector_id}' is not registered")
        return connector

    def iter_routers(self) -> Iterable[APIRouter]:
        return self._routers.values()

    def iter_inbound(self) -> Iterable[InboundConnector]:
        return self._inbound.values()

    def notify_shutdown(self) -> None:
        if not self._tracer:
            return
        for connector in self._inbound.values():
            tags = self._tracer.connector_tags(
                connector_id=connector.connector_id,
                connector_type=connector.connector_type.value,
                extra=["connector", "inbound", "shutdown"],
            )
            self._tracer.record_event(
                "connector.detached",
                metadata={
                    "connector_id": connector.connector_id,
                    "connector_type": connector.connector_type.value,
                    "direction": "inbound",
                },
                tags=tags,
            )
