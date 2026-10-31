from fastapi import Request

from common import SalesAgentSettings as Settings

from src.sales_agent.connectors.registry import ConnectorRegistry
from src.sales_agent.core.llm.client import LLMClient
from src.sales_agent.core.telemetry import Tracer
from src.sales_agent.services.backend_client import BackendClient
from src.sales_agent.services.debounce import DebounceManager


def get_debouncer(request: Request) -> DebounceManager:
    """
    Provide DebounceManager instance from app.state.
    """
    return request.app.state.debouncer


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_connector_registry(request: Request) -> ConnectorRegistry:
    registry = getattr(request.app.state, "connector_registry", None)
    if registry is None:
        raise RuntimeError("Connector registry is not initialized")
    return registry


def get_large_llm_client(request: Request) -> LLMClient:
    """Provide LLMClient instance from app.state."""
    return request.app.state.large_llm_client


def get_tracer(request: Request) -> Tracer:
    """Provide Tracer instance from app.state."""
    return request.app.state.tracer


def get_backend_client(request: Request) -> BackendClient:
    """Provide BackendClient instance from app.state."""
    return request.app.state.backend_client
