"""Broker abstraction for event publishing and consumption."""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol

from common.events.envelope import EventEnvelope


@dataclass(frozen=True, slots=True)
class StreamConfig:
    """Configuration for connecting to a single event stream."""

    stream_name: str
    group: str
    consumer_name: str
    block_ms: int = 5000
    count: int = 10


@dataclass(frozen=True, slots=True)
class ReceivedEvent:
    """Event received from broker with delivery metadata."""

    envelope: EventEnvelope
    stream_name: str
    message_id: str
    raw_data: bytes


class EventBroker(ABC):
    """
    Abstract broker interface for event publishing and consumption.

    Implementations: RedisStreamsBroker (production), InMemoryBroker (tests).
    """

    @abstractmethod
    async def publish(self, stream_name: str, envelope: EventEnvelope) -> str:
        """
        Publish an event to a stream.

        Args:
            stream_name: Target stream name (e.g., "backend.events")
            envelope: Event envelope to publish

        Returns:
            Message ID assigned by the broker
        """
        ...

    @abstractmethod
    def subscribe(self, config: StreamConfig) -> AsyncIterator[ReceivedEvent]:
        """
        Subscribe to a stream using consumer groups.

        Yields events one at a time. The caller must ACK after processing.

        Args:
            config: Stream configuration

        Yields:
            ReceivedEvent instances
        """
        ...

    @abstractmethod
    async def ack(self, config: StreamConfig, message_id: str) -> None:
        """
        Acknowledge successful processing of a message.

        Args:
            config: Stream configuration (for group info)
            message_id: ID of the message to acknowledge
        """
        ...

    @abstractmethod
    async def ensure_group(self, config: StreamConfig) -> None:
        """
        Ensure consumer group exists for the stream.

        Creates the group if it doesn't exist. Safe to call multiple times.

        Args:
            config: Stream configuration
        """
        ...

    @abstractmethod
    async def close(self) -> None:
        """Close broker connections and clean up resources."""
        ...


class BrokerFactory(Protocol):
    """Protocol for broker factory functions (DI support)."""

    def __call__(self, redis_url: str) -> EventBroker: ...
