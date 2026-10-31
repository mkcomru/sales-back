from contextlib import asynccontextmanager

from fastapi import FastAPI

from common import log

from src.sales_agent.api import internal, simulator
from src.sales_agent.connectors.http import build_universal_webhook_router


@asynccontextmanager
async def routers_lifespan(app: FastAPI):
    connector_registry = app.state.connector_registry

    for router in connector_registry.iter_routers():
        app.include_router(router)

    universal_router = build_universal_webhook_router()
    app.include_router(universal_router)

    # Internal inbound endpoint (Plan 010)
    app.include_router(internal.router)
    app.include_router(internal.tasks_router)
    app.include_router(internal.debounce_router)
    app.include_router(internal.transcription_router)

    app.include_router(simulator.router)

    log.info("http.start", mode="connector_webhook")

    yield

    log.info("app.stop")
