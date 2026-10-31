"""Tests for API dependencies."""

from __future__ import annotations

from unittest.mock import MagicMock

from fastapi import FastAPI, Request

from wappi_module.api.dependencies import (
    get_connector_manager,
    get_sales_agent_client,
    get_transport_service,
    get_wappi_client,
)
from wappi_module.connectors.manager import ConnectorManager
from wappi_module.services.sales_agent import BackendInboundClient
from wappi_module.services.wappi_api import WappiApiClient
from wappi_module.transport.service import TransportDeliveryService


class TestDependencies:
    def test_get_connector_manager(self, mock_connector_manager: ConnectorManager) -> None:
        app = FastAPI()
        app.state.connector_manager = mock_connector_manager

        request = MagicMock(spec=Request)
        request.app = app

        result = get_connector_manager(request)

        assert result is mock_connector_manager

    def test_get_sales_agent_client(self, mock_sales_agent_client: BackendInboundClient) -> None:
        app = FastAPI()
        app.state.sales_agent_client = mock_sales_agent_client

        request = MagicMock(spec=Request)
        request.app = app

        result = get_sales_agent_client(request)

        assert result is mock_sales_agent_client

    def test_get_transport_service(self, mock_transport_service: TransportDeliveryService) -> None:
        app = FastAPI()
        app.state.transport_service = mock_transport_service

        request = MagicMock(spec=Request)
        request.app = app

        result = get_transport_service(request)

        assert result is mock_transport_service

    def test_get_wappi_client(self, mock_wappi_api_client: WappiApiClient) -> None:
        app = FastAPI()
        app.state.wappi_client = mock_wappi_api_client

        request = MagicMock(spec=Request)
        request.app = app

        result = get_wappi_client(request)

        assert result is mock_wappi_api_client
