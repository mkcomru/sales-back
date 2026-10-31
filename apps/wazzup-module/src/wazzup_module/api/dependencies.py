from __future__ import annotations

import secrets

from fastapi import HTTPException, Request, status

from wazzup_module.config import Settings, get_settings
from wazzup_module.connectors.manager import ConnectorManager
from wazzup_module.services.backend import WazzupBackendClient
from wazzup_module.services.inbound import BackendInboundClient
from wazzup_module.services.wazzup_api import WazzupApiClient
from wazzup_module.transport.service import TransportDeliveryService


def get_connector_manager(request: Request) -> ConnectorManager:
    return request.app.state.connector_manager


def get_inbound_client(request: Request) -> BackendInboundClient:
    return request.app.state.inbound_client


def get_transport_service(request: Request) -> TransportDeliveryService:
    return request.app.state.transport_service


def get_wazzup_client(request: Request) -> WazzupApiClient:
    return request.app.state.wazzup_client


def get_backend_client(request: Request) -> WazzupBackendClient:
    return request.app.state.backend_client


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


def require_service_api_key(request: Request) -> None:
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
