from contextlib import asynccontextmanager

from fastapi import FastAPI

from common import SalesAgentSettings, setup_logging


@asynccontextmanager
async def logging_lifespan(app: FastAPI):
    settings: SalesAgentSettings = app.state.settings
    setup_logging(environment=settings.app.environment, debug=settings.app.debug)
    yield
