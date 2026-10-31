from contextlib import asynccontextmanager

from fastapi import FastAPI

from common import SalesAgentSettings

from src.sales_agent.connectors import build_connector_registry
from src.sales_agent.core.telemetry import Tracer
from src.sales_agent.services.backend_client import BackendClient
from src.sales_agent.services.connector_sync import ConnectorSync
from src.sales_agent.services.debounce import DebounceManager
from src.sales_agent.services.message_processor import create_batch_processor


@asynccontextmanager
async def connectors_lifespan(app: FastAPI):
    settings: SalesAgentSettings = app.state.settings
    tracer: Tracer = app.state.tracer
    backend_client: BackendClient = app.state.backend_client

    connector_registry = build_connector_registry(settings, tracer=tracer)
    app.state.connector_registry = connector_registry

    connector_sync = ConnectorSync(settings, backend_client, registry=connector_registry, tracer=tracer)
    app.state.connector_sync = connector_sync
    await connector_sync.bootstrap()
    await connector_sync.start()

    on_batch_callback = create_batch_processor(
        app=app,
        settings=settings,
        backend_client=backend_client,
        large_llm_client=app.state.large_llm_client,
        tracer=tracer,
        crm_adapter=app.state.crm_adapter,
    )

    connector_for_window = settings.get_default_connector()
    window = settings.debounce.window_seconds
    if connector_for_window is not None:
        window = connector_for_window.debounce.resolve_window(window)

    app.state.debouncer = DebounceManager(on_batch_callback=on_batch_callback, debounce_seconds=window)  # type: ignore[attr-defined]

    yield

    await connector_sync.stop()
    connector_registry.notify_shutdown()
