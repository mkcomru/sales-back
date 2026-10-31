"""In-memory broker implementation for testing."""

import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from uuid import uuid4

from common.events.broker import EventBroker, ReceivedEvent, StreamConfig
from common.events.codec import encode_envelope
from common.events.envelope import EventEnvelope


@dataclass
class StoredMessage:
    """Message stored in the in-memory stream."""

    message_id: str
    envelope: EventEnvelope
    raw_data: bytes
    delivered_to: set[str] = field(default_factory=set)
    acked_by: set[str] = field(default_factory=set)


class InMemoryBroker(EventBroker):
    """
    In-memory broker for testing.

    Features:
    - Stores messages per stream
    - Tracks delivery and ACK per consumer group
    - Supports blocking subscribe with timeout
    """

    def __init__(self) -> None:
        self._streams: dict[str, list[StoredMessage]] = defaultdict(list)
        self._groups: dict[str, set[str]] = defaultdict(set)
        self._events: dict[str, asyncio.Event] = defaultdict(asyncio.Event)
        self._closed = False

    async def publish(self, stream_name: str, envelope: EventEnvelope) -> str:
        """Publish an event to the in-memory stream."""
        message_id = f"{stream_name}-{uuid4().hex[:8]}"
        raw_data = encode_envelope(envelope)

        message = StoredMessage(
            message_id=message_id,
            envelope=envelope,
            raw_data=raw_data,
        )
        self._streams[stream_name].append(message)

        event = self._events.get(stream_name)
        if event:
            event.set()

        return message_id

    def subscribe(self, config: StreamConfig) -> AsyncIterator[ReceivedEvent]:
        """Subscribe to a stream, yielding undelivered messages."""
        return self._subscribe_impl(config)

    async def _subscribe_impl(self, config: StreamConfig) -> AsyncIterator[ReceivedEvent]:
        """Actual subscribe implementation as async generator."""
        group_key = f"{config.stream_name}:{config.group}"

        while not self._closed:
            messages = self._streams.get(config.stream_name, [])

            for message in messages:
                if group_key in message.delivered_to:
                    continue

                message.delivered_to.add(group_key)

                yield ReceivedEvent(
                    envelope=message.envelope,
                    stream_name=config.stream_name,
                    message_id=message.message_id,
                    raw_data=message.raw_data,
                )

            event = self._events[config.stream_name]
            event.clear()
            try:
                await asyncio.wait_for(
                    event.wait(),
                    timeout=config.block_ms / 1000.0,
                )
            except TimeoutError:
                pass

    async def ack(self, config: StreamConfig, message_id: str) -> None:
        """Mark a message as acknowledged."""
        group_key = f"{config.stream_name}:{config.group}"
        messages = self._streams.get(config.stream_name, [])

        for message in messages:
            if message.message_id == message_id:
                message.acked_by.add(group_key)
                break

    async def ensure_group(self, config: StreamConfig) -> None:
        """Register a consumer group (no-op for in-memory)."""
        self._groups[config.stream_name].add(config.group)

    async def close(self) -> None:
        """Close the broker."""
        self._closed = True
        for event in self._events.values():
            event.set()

    def get_messages(self, stream_name: str) -> list[StoredMessage]:
        """Get all messages in a stream (test helper)."""
        return self._streams.get(stream_name, [])

    def get_unacked_messages(self, stream_name: str, group: str) -> list[StoredMessage]:
        """Get unacked messages for a consumer group (test helper)."""
        group_key = f"{stream_name}:{group}"
        messages = self._streams.get(stream_name, [])
        return [m for m in messages if group_key not in m.acked_by]

    def clear(self) -> None:
        """Clear all messages (test helper)."""
        self._streams.clear()
        self._groups.clear()
