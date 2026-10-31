from contextlib import asynccontextmanager

from fastapi import FastAPI

from common import SalesAgentSettings

from src.sales_agent.core.telemetry import get_tracer


@asynccontextmanager
async def telemetry_lifespan(app: FastAPI):
    settings: SalesAgentSettings = app.state.settings
    tracer = get_tracer(settings)
    app.state.tracer = tracer
    yield
