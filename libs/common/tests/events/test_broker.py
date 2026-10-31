"""Tests for in-memory broker."""

import asyncio

import pytest

from common.events.broker import StreamConfig
from common.events.envelope import EventEnvelope, EventName, Producer
from common.events.testing import InMemoryBroker


@pytest.fixture
def broker() -> InMemoryBroker:
    return InMemoryBroker()


@pytest.fixture
def stream_config() -> StreamConfig:
    return StreamConfig(
        stream_name="backend.events",
        group="test-group",
        consumer_name="test-consumer",
        block_ms=100,
    )


@pytest.fixture
def envelope() -> EventEnvelope:
    return EventEnvelope(
        event_name=EventName.TRANSPORT_CONNECTORS_CHANGED,
        event_version=1,
        producer=Producer.BACKEND,
        dedupe_key="test-broker",
    )


class TestInMemoryBroker:
    async def test_publish_stores_message(
        self,
        broker: InMemoryBroker,
        envelope: EventEnvelope,
    ) -> None:
        message_id = await broker.publish("backend.events", envelope)

        assert message_id is not None
        messages = broker.get_messages("backend.events")
        assert len(messages) == 1
        assert messages[0].envelope == envelope

    async def test_subscribe_yields_messages(
        self,
        broker: InMemoryBroker,
        stream_config: StreamConfig,
        envelope: EventEnvelope,
    ) -> None:
        await broker.publish("backend.events", envelope)

        received = []
        async for event in broker.subscribe(stream_config):
            received.append(event)
            break

        assert len(received) == 1
        assert received[0].envelope == envelope

    async def test_ack_marks_message(
        self,
        broker: InMemoryBroker,
        stream_config: StreamConfig,
        envelope: EventEnvelope,
    ) -> None:
        await broker.publish("backend.events", envelope)

        async for event in broker.subscribe(stream_config):
            await broker.ack(stream_config, event.message_id)
            break

        unacked = broker.get_unacked_messages("backend.events", "test-group")
        assert len(unacked) == 0

    async def test_different_groups_get_same_message(
        self,
        broker: InMemoryBroker,
        envelope: EventEnvelope,
    ) -> None:
        await broker.publish("backend.events", envelope)

        config1 = StreamConfig(
            stream_name="backend.events",
            group="group-1",
            consumer_name="consumer-1",
            block_ms=100,
        )

        config2 = StreamConfig(
            stream_name="backend.events",
            group="group-2",
            consumer_name="consumer-2",
            block_ms=100,
        )

        received_by_1 = []
        async for event in broker.subscribe(config1):
            received_by_1.append(event)
            break

        received_by_2 = []
        async for event in broker.subscribe(config2):
            received_by_2.append(event)
            break

        assert len(received_by_1) == 1
        assert len(received_by_2) == 1
        assert received_by_1[0].envelope == received_by_2[0].envelope

    async def test_ensure_group_is_idempotent(
        self,
        broker: InMemoryBroker,
        stream_config: StreamConfig,
    ) -> None:
        await broker.ensure_group(stream_config)
        await broker.ensure_group(stream_config)

    async def test_close_stops_subscription(
        self,
        broker: InMemoryBroker,
        stream_config: StreamConfig,
    ) -> None:
        async def consume() -> int:
            count = 0
            async for _ in broker.subscribe(stream_config):
                count += 1
            return count

        task = asyncio.create_task(consume())
        await asyncio.sleep(0.05)
        await broker.close()

        count = await asyncio.wait_for(task, timeout=1.0)
        assert count == 0

    async def test_clear_removes_messages(
        self,
        broker: InMemoryBroker,
        envelope: EventEnvelope,
    ) -> None:
        await broker.publish("backend.events", envelope)
        broker.clear()

        messages = broker.get_messages("backend.events")
        assert len(messages) == 0
