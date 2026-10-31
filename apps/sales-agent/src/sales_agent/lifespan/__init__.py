from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI

from src.sales_agent.lifespan.clients import clients_lifespan
from src.sales_agent.lifespan.connectors import connectors_lifespan
from src.sales_agent.lifespan.eventing import eventing_lifespan
from src.sales_agent.lifespan.logging import logging_lifespan
from src.sales_agent.lifespan.routers import routers_lifespan
from src.sales_agent.lifespan.settings import settings_lifespan
from src.sales_agent.lifespan.telemetry import telemetry_lifespan


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with AsyncExitStack() as stack:
        await stack.enter_async_context(settings_lifespan(app))
        await stack.enter_async_context(logging_lifespan(app))
        await stack.enter_async_context(telemetry_lifespan(app))
        await stack.enter_async_context(clients_lifespan(app))
        await stack.enter_async_context(connectors_lifespan(app))
        await stack.enter_async_context(eventing_lifespan(app))
        await stack.enter_async_context(routers_lifespan(app))
        yield
