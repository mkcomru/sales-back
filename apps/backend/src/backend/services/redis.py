from functools import lru_cache

import redis.asyncio as aioredis
import structlog
from pydantic import BaseModel

from src.backend.modules.core.settings import get_settings

log = structlog.get_logger(__name__)


class WsTicketPayload(BaseModel):
    user_id: int
    company_id: int
    role: str


class RedisKVClient:
    def __init__(self, redis_url: str) -> None:
        self._client: aioredis.Redis = aioredis.from_url(redis_url, decode_responses=True)

    async def set_with_ttl(self, key: str, value: WsTicketPayload, ttl: int) -> None:
        await self._client.set(key, value.model_dump_json(), ex=ttl)

    async def get_and_delete(self, key: str) -> WsTicketPayload | None:
        raw = await self._client.getdel(key)
        if raw is None:
            return None
        return WsTicketPayload.model_validate_json(raw)

    async def close(self) -> None:
        await self._client.aclose()


@lru_cache
def get_redis_client() -> RedisKVClient:
    settings = get_settings()
    if not settings.redis.url:
        raise RuntimeError("REDIS__URL is not configured")
    return RedisKVClient(settings.redis.url)
