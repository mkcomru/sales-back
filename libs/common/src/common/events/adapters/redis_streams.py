"""Redis Streams implementation of the EventBroker interface."""

import asyncio
from collections.abc import AsyncIterator

import structlog

from common.events.broker import EventBroker, ReceivedEvent, StreamConfig
from common.events.codec import decode_envelope, encode_envelope
from common.events.envelope import EventEnvelope

log = structlog.get_logger(__name__)

try:
    import redis.asyncio as redis
    from redis.exceptions import ResponseError
except ImportError as exc:
    raise ImportError("redis package required for RedisStreamsBroker. Install with: pip install redis") from exc


class RedisStreamsBroker(EventBroker):
    """
    Redis Streams implementation of EventBroker.

    Uses consumer groups for at-least-once delivery semantics.
    """

    def __init__(
        self,
        redis_url: str,
        connection_pool: redis.ConnectionPool | None = None,
    ) -> None:
        self._redis_url = redis_url
        self._pool = connection_pool
        self._client: redis.Redis | None = None

    async def _get_client(self) -> redis.Redis:
        """Get or create Redis client."""
        if self._client is None:
            if self._pool:
                self._client = redis.Redis(connection_pool=self._pool)
            else:
                self._client = redis.from_url(
                    self._redis_url,
                    decode_responses=False,
                )
        return self._client

    async def publish(self, stream_name: str, envelope: EventEnvelope) -> str:
        """Publish an event to a Redis Stream."""
        client = await self._get_client()
        data = encode_envelope(envelope)

        message_id: bytes = await client.xadd(
            stream_name,
            {"data": data},
            maxlen=10000,
            approximate=True,
        )

        msg_id = message_id.decode() if isinstance(message_id, bytes) else message_id
        log.debug(
            "redis_streams.published",
            stream=stream_name,
            event_name=envelope.event_name,
            event_id=str(envelope.event_id),
            message_id=msg_id,
        )

        return message_id.decode() if isinstance(message_id, bytes) else str(message_id)

    def subscribe(self, config: StreamConfig) -> AsyncIterator[ReceivedEvent]:
        """Subscribe to a Redis Stream using consumer groups."""
        return self._subscribe_impl(config)

    async def _subscribe_impl(self, config: StreamConfig) -> AsyncIterator[ReceivedEvent]:
        """Actual subscribe implementation as async generator."""
        client = await self._get_client()

        log.info(
            "redis_streams.subscribing",
            stream=config.stream_name,
            group=config.group,
            consumer=config.consumer_name,
        )

        while True:
            try:
                messages = await client.xreadgroup(
                    groupname=config.group,
                    consumername=config.consumer_name,
                    streams={config.stream_name: ">"},
                    count=config.count,
                    block=config.block_ms,
                )

                if not messages:
                    continue

                for stream_name_bytes, stream_messages in messages:
                    stream_name = (
                        stream_name_bytes.decode() if isinstance(stream_name_bytes, bytes) else stream_name_bytes
                    )

                    for message_id_bytes, fields in stream_messages:
                        message_id = (
                            message_id_bytes.decode() if isinstance(message_id_bytes, bytes) else message_id_bytes
                        )

                        raw_data = fields.get(b"data") or fields.get("data")
                        if raw_data is None:
                            log.warning(
                                "redis_streams.missing_data",
                                stream=stream_name,
                                message_id=message_id,
                            )
                            await self.ack(config, message_id)
                            continue

                        if isinstance(raw_data, str):
                            raw_data = raw_data.encode()

                        try:
                            envelope = decode_envelope(raw_data)
                        except Exception as exc:
                            log.error(
                                "redis_streams.decode_failed",
                                stream=stream_name,
                                message_id=message_id,
                                error=str(exc),
                            )
                            await self.ack(config, message_id)
                            continue

                        yield ReceivedEvent(
                            envelope=envelope,
                            stream_name=stream_name,
                            message_id=message_id,
                            raw_data=raw_data,
                        )

            except asyncio.CancelledError:
                log.debug(
                    "redis_streams.subscription_cancelled",
                    stream=config.stream_name,
                )
                raise

    async def ack(self, config: StreamConfig, message_id: str) -> None:
        """Acknowledge a message in Redis Stream."""
        client = await self._get_client()
        await client.xack(
            config.stream_name,
            config.group,
            message_id,
        )
        log.debug(
            "redis_streams.acked",
            stream=config.stream_name,
            group=config.group,
            message_id=message_id,
        )

    async def ensure_group(self, config: StreamConfig) -> None:
        """Ensure consumer group exists, creating if necessary."""
        client = await self._get_client()

        try:
            await client.xgroup_create(
                config.stream_name,
                config.group,
                id="0",
                mkstream=True,
            )
            log.info(
                "redis_streams.group_created",
                stream=config.stream_name,
                group=config.group,
            )
        except ResponseError as exc:
            if "BUSYGROUP" in str(exc):
                log.debug(
                    "redis_streams.group_exists",
                    stream=config.stream_name,
                    group=config.group,
                )
            else:
                raise

    async def close(self) -> None:
        """Close Redis connection."""
        if self._client:
            await self._client.aclose()
            self._client = None
            log.debug("redis_streams.closed")


def create_redis_broker(redis_url: str) -> RedisStreamsBroker:
    """Factory function for creating RedisStreamsBroker (DI support)."""
    return RedisStreamsBroker(redis_url)
