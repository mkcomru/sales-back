from __future__ import annotations

import secrets

from fastapi import HTTPException, Request, status

from wappi_module.config import Settings, get_settings
from wappi_module.connectors.manager import ConnectorManager
from wappi_module.services.backend import WappiBackendClient
from wappi_module.services.sales_agent import BackendInboundClient
from wappi_module.services.wappi_api import WappiApiClient
from wappi_module.sync.controller import SyncController
from wappi_module.transport.service import TransportDeliveryService


def get_connector_manager(request: Request) -> ConnectorManager:
    return request.app.state.connector_manager


def get_sales_agent_client(request: Request) -> BackendInboundClient:
    return request.app.state.sales_agent_client


def get_transport_service(request: Request) -> TransportDeliveryService:
    return request.app.state.transport_service


def get_wappi_client(request: Request) -> WappiApiClient:
    return request.app.state.wappi_client


def get_sync_controller(request: Request) -> SyncController:
    return request.app.state.sync_controller


def get_backend_client(request: Request) -> WappiBackendClient:
    return request.app.state.backend_client


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


def require_service_api_key(request: Request) -> None:
    """Require valid service API key in request headers."""
    settings = get_settings()
    service_key = settings.service.api_key
    if service_key is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service API key not configured",
        )

    header_name = settings.service.resolved_header()
    provided = request.headers.get(header_name)
    if not provided or not secrets.compare_digest(provided, service_key.get_secret_value()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid service API key",
        )
