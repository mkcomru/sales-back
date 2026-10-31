from contextlib import asynccontextmanager

from fastapi import FastAPI

from common import SalesAgentSettings


@asynccontextmanager
async def settings_lifespan(app: FastAPI):
    settings = SalesAgentSettings()
    app.state.settings = settings
    yield
