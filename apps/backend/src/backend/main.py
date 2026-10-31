from contextlib import asynccontextmanager

import sentry_sdk
import structlog
from fastapi import FastAPI, status
from fastapi.responses import Response
from sentry_sdk.integrations.asyncpg import AsyncPGIntegration
from sentry_sdk.integrations.fastapi import FastApiIntegration
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from common import setup_logging
from common.events.adapters import RedisStreamsBroker
from common.fastapi import apply_cors

from src.backend import db
from src.backend.modules import router
from src.backend.modules.core.exceptions import exception_handlers
from src.backend.modules.core.settings import get_settings
from src.backend.modules.forms.rate_limit import limiter
from src.backend.services.events.publisher import BackendEventPublisher, set_event_publisher
from src.backend.services.redis import get_redis_client

log = structlog.get_logger(__name__)

settings = get_settings()

if settings.sentry.is_enabled():
    sentry_sdk.init(
        dsn=settings.sentry.dsn,
        send_default_pii=settings.sentry.send_default_pii,
        traces_sample_rate=settings.sentry.traces_sample_rate,
        environment=settings.sentry.environment or settings.app.environment,
        integrations=[
            FastApiIntegration(),
            AsyncPGIntegration(),
        ],
    )
    log.info("Sentry initialized")


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(environment=settings.app.environment, debug=settings.app.debug)
    log.info("Entering application lifespan")

    await db.init()

    log.info(
        "Eventing config: enabled=%s, redis_url=%s, stream=%s",
        settings.eventing.enabled,
        bool(settings.redis.url),
        settings.eventing.stream.name,
    )

    if settings.redis.url:
        get_redis_client()
        log.info("Redis KV client initialized")

    publisher: BackendEventPublisher | None = None
    if settings.eventing.enabled and settings.redis.url:
        broker = RedisStreamsBroker(settings.redis.url)
        publisher = BackendEventPublisher(
            broker,
            stream_name=settings.eventing.stream.name,
            enabled=True,
        )
        set_event_publisher(publisher)
        log.info("Event publisher initialized (stream=%s)", settings.eventing.stream.name)
    else:
        log.info("Event publisher disabled")

    yield

    if publisher:
        await publisher.close()
        set_event_publisher(None)
        log.info("Event publisher closed")

    if settings.redis.url:
        await get_redis_client().close()
        log.info("Redis KV client closed")

    await db.close()

    log.info("Resources cleaned up")


exception_handlers_with_rate_limit = {**exception_handlers, RateLimitExceeded: _rate_limit_exceeded_handler}
app = FastAPI(lifespan=lifespan, exception_handlers=exception_handlers_with_rate_limit)
apply_cors(app, settings.cors)

app.state.limiter = limiter
app.include_router(router)


@app.get("/health")
async def check_health() -> Response:
    return Response(status_code=status.HTTP_200_OK)
