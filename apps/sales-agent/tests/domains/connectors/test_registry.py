"""Tests for connector registry module."""

from __future__ import annotations

from collections.abc import Sequence
from unittest.mock import MagicMock

import pytest
from fastapi import APIRouter

from src.sales_agent.connectors.base import (
    ConnectorType,
    InboundConnector,
    InboundPayload,
)
from src.sales_agent.connectors.registry import ConnectorRegistry
from src.sales_agent.services.debounce import IncomingMessage


class MockInboundConnector(InboundConnector):
    """Mock inbound connector for testing."""

    def __init__(self, connector_id: str, connector_type: ConnectorType = ConnectorType.MESSAGING) -> None:
        self._connector_id = connector_id
        self._connector_type = connector_type

    @property
    def connector_id(self) -> str:
        return self._connector_id

    @property
    def connector_type(self) -> ConnectorType:
        return self._connector_type

    async def normalize(self, payload: InboundPayload) -> Sequence[IncomingMessage]:
        return []


class TestConnectorRegistry:
    """Test ConnectorRegistry class."""

    def test_register_inbound(self) -> None:
        """Test registering an inbound connector."""
        registry = ConnectorRegistry()
        connector = MockInboundConnector("test-connector")
        router = APIRouter()

        registry.register_inbound(connector, router)

        assert registry.get_inbound("test-connector") is connector
        routers = list(registry.iter_routers())
        assert router in routers

    def test_get_inbound_existing(self) -> None:
        """Test getting existing inbound connector."""
        registry = ConnectorRegistry()
        connector = MockInboundConnector("test-connector")
        router = APIRouter()

        registry.register_inbound(connector, router)
        result = registry.get_inbound("test-connector")

        assert result is connector

    def test_get_inbound_nonexistent(self) -> None:
        """Test getting non-existent connector returns None."""
        registry = ConnectorRegistry()
        result = registry.get_inbound("nonexistent")
        assert result is None

    def test_require_inbound_existing(self) -> None:
        """Test require_inbound returns connector when exists."""
        registry = ConnectorRegistry()
        connector = MockInboundConnector("test-connector")
        router = APIRouter()

        registry.register_inbound(connector, router)
        result = registry.require_inbound("test-connector")

        assert result is connector

    def test_require_inbound_nonexistent_raises(self) -> None:
        """Test require_inbound raises LookupError when connector doesn't exist."""
        registry = ConnectorRegistry()

        with pytest.raises(LookupError, match="not registered"):
            registry.require_inbound("nonexistent")

    def test_iter_routers(self) -> None:
        """Test iterating over routers."""
        registry = ConnectorRegistry()
        router1 = APIRouter()
        router2 = APIRouter()
        connector1 = MockInboundConnector("connector-1")
        connector2 = MockInboundConnector("connector-2")

        registry.register_inbound(connector1, router1)
        registry.register_inbound(connector2, router2)

        routers = list(registry.iter_routers())
        assert len(routers) == 2
        assert router1 in routers
        assert router2 in routers

    def test_iter_inbound(self) -> None:
        """Test iterating over inbound connectors."""
        registry = ConnectorRegistry()
        connector1 = MockInboundConnector("connector-1")
        connector2 = MockInboundConnector("connector-2")
        router = APIRouter()

        registry.register_inbound(connector1, router)
        registry.register_inbound(connector2, router)

        connectors = list(registry.iter_inbound())
        assert len(connectors) == 2
        assert connector1 in connectors
        assert connector2 in connectors

    def test_notify_shutdown_without_tracer(self) -> None:
        """Test notify_shutdown without tracer does nothing."""
        registry = ConnectorRegistry()
        connector = MockInboundConnector("test-connector")
        router = APIRouter()

        registry.register_inbound(connector, router)
        registry.notify_shutdown()  # Should not raise

    def test_notify_shutdown_with_tracer(self) -> None:
        """Test notify_shutdown with tracer records events."""
        mock_tracer = MagicMock()
        registry = ConnectorRegistry(tracer=mock_tracer)
        connector = MockInboundConnector("test-connector")
        router = APIRouter()

        registry.register_inbound(connector, router)
        registry.notify_shutdown()

        assert mock_tracer.record_event.called

    def test_register_multiple_connectors(self) -> None:
        """Test registering multiple connectors."""
        registry = ConnectorRegistry()
        connectors = [MockInboundConnector(f"connector-{i}") for i in range(5)]
        router = APIRouter()

        for connector in connectors:
            registry.register_inbound(connector, router)

        assert len(list(registry.iter_inbound())) == 5
        for i, connector in enumerate(connectors):
            assert registry.get_inbound(f"connector-{i}") is connector
