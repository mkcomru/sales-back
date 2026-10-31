import time
from contextlib import asynccontextmanager

from fastapi import FastAPI

from common import SalesAgentSettings, log

from src.sales_agent.core.llm.client import LLMClient
from src.sales_agent.core.telemetry import Tracer
from src.sales_agent.services.backend_client import BackendClient
from src.sales_agent.services.crm_adapter import CRMAdapter
from src.sales_agent.storage.customer_store import set_backend_client


@asynccontextmanager
async def clients_lifespan(app: FastAPI):
    settings: SalesAgentSettings = app.state.settings
    tracer: Tracer = app.state.tracer

    crm_adapter = CRMAdapter(settings)
    app.state.crm_adapter = crm_adapter

    large_llm_client = LLMClient.from_settings(settings, model=settings.llm.large_model)
    app.state.large_llm_client = large_llm_client

    backend_client = BackendClient(settings)
    app.state.backend_client = backend_client

    set_backend_client(backend_client, company_id=1)

    t0 = time.time()
    tracer.flush()
    dt = int((time.time() - t0) * 1000)
    log.info("langfuse.probe", probe_ms=dt)

    log.info(
        "app.start",
        version=settings.app.version,
        environment=settings.app.environment,
        debug=settings.app.debug,
        db_url=("sqlite" if (settings.database.url or "").startswith("sqlite") else "other"),
        redis_enabled=bool(settings.redis.url),
        langfuse_enabled=settings.langfuse.enabled,
        langfuse_host=settings.langfuse.host,
        llm_light_model=settings.llm.light_model,
        llm_large_model=settings.llm.large_model,
        llm_base_url=settings.llm.base_url,
    )

    yield

    await backend_client.close_chat_client()
