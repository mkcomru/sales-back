from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack, asynccontextmanager, suppress

import structlog
from fastapi import FastAPI

from common import AudioConversionService, log, setup_logging
from common.fastapi import apply_cors
from common.transport.registry import CONNECTOR_TYPE_CATALOG
from common.transport.validation import validate_connector_module
from wazzup_module.api.routes import (
    admin_router,
    health_router,
    transport_router,
    wazzup_router,
)
from wazzup_module.config import Settings, get_settings
from wazzup_module.connectors.manager import ConnectorManager
from wazzup_module.lifespan.eventing import eventing_lifespan
from wazzup_module.services.backend import WazzupBackendClient
from wazzup_module.services.inbound import BackendInboundClient
from wazzup_module.services.wazzup_api import WazzupApiClient
from wazzup_module.transport.service import TransportDeliveryService

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with AsyncExitStack() as stack:
        settings: Settings = get_settings()
        setup_logging(environment=settings.app.environment, debug=settings.app.debug)

        backend_client = WazzupBackendClient(settings)
        inbound_client = BackendInboundClient(settings, backend_client, AudioConversionService())
        wazzup_client = WazzupApiClient()
        connector_manager = ConnectorManager(settings, backend_client, wazzup_client)
        transport_service = TransportDeliveryService(settings, connector_manager)

        wazzup_entries = [e for e in CONNECTOR_TYPE_CATALOG.values() if e.connector_type.startswith("wazzup")]
        validate_connector_module(wazzup_entries, transport_service)

        app.state.settings = settings
        app.state.connector_manager = connector_manager
        app.state.inbound_client = inbound_client
        app.state.transport_service = transport_service
        app.state.wazzup_client = wazzup_client
        app.state.backend_client = backend_client

        reload_task: asyncio.Task[None] | None = None

        async def periodic_reload(interval: float) -> None:
            try:
                while True:
                    await asyncio.sleep(interval)
                    current_task = asyncio.current_task()
                    if current_task is not None and current_task.cancelled():
                        raise asyncio.CancelledError
                    try:
                        await connector_manager.reload()
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        logger.warning("connector.reload.background_failed", error=str(exc))
            except asyncio.CancelledError:
                logger.debug("periodic_reload.cancelled")
                raise

        await connector_manager.reload()
        interval = max(settings.config_refresh_interval_s, 0.0)
        if interval > 0:
            reload_task = asyncio.create_task(periodic_reload(interval))
            app.state.reload_task = reload_task

        await stack.enter_async_context(eventing_lifespan(app))

        log.info(
            "app.start",
            environment=settings.app.environment,
        )
        try:
            yield
        finally:
            logger.info("app.shutdown.starting")
            reload_task_to_cancel = reload_task or getattr(app.state, "reload_task", None)
            if reload_task_to_cancel and not reload_task_to_cancel.done():
                reload_task_to_cancel.cancel()
                with suppress(asyncio.CancelledError):
                    await reload_task_to_cancel
            await connector_manager.shutdown()
            logger.info("app.shutdown.completed")


app = FastAPI(title="Sales Bot Wazzup Module", lifespan=lifespan)
apply_cors(app, get_settings().cors)

app.include_router(transport_router)
app.include_router(admin_router)
app.include_router(health_router)
app.include_router(wazzup_router)
