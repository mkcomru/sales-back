"""Tests for consumer runner."""

import asyncio

import pytest

from common.events.broker import StreamConfig
from common.events.envelope import EventEnvelope, EventName, Producer
from common.events.registry import ConsumerRegistry
from common.events.runner import ConsumerRunner
from common.events.testing import InMemoryBroker, create_test_runner_deps


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
        dedupe_key="test-runner",
        payload={"change_type": "upsert"},
    )


class TestConsumerRunner:
    async def test_runner_processes_event(
        self,
        broker: InMemoryBroker,
        stream_config: StreamConfig,
        envelope: EventEnvelope,
    ) -> None:
        handled_events: list[EventEnvelope] = []

        async def handler(env: EventEnvelope) -> None:
            handled_events.append(env)

        registry = ConsumerRegistry()
        registry.register(handler)

        deps = create_test_runner_deps(broker=broker)
        runner = ConsumerRunner(
            registry=registry,
            config=stream_config,
            deps=deps,
        )

        await broker.publish("backend.events", envelope)

        await runner.start()
        await asyncio.sleep(0.15)
        await runner.stop()

        assert len(handled_events) == 1
        assert handled_events[0].dedupe_key == envelope.dedupe_key

    async def test_runner_acks_after_success(
        self,
        broker: InMemoryBroker,
        stream_config: StreamConfig,
        envelope: EventEnvelope,
    ) -> None:
        async def handler(env: EventEnvelope) -> None:
            pass

        registry = ConsumerRegistry()
        registry.register(handler)

        deps = create_test_runner_deps(broker=broker)
        runner = ConsumerRunner(
            registry=registry,
            config=stream_config,
            deps=deps,
        )

        await broker.publish("backend.events", envelope)

        await runner.start()
        await asyncio.sleep(0.15)
        await runner.stop()

        unacked = broker.get_unacked_messages("backend.events", "test-group")
        assert len(unacked) == 0

    async def test_runner_does_not_ack_on_failure(
        self,
        broker: InMemoryBroker,
        stream_config: StreamConfig,
        envelope: EventEnvelope,
    ) -> None:
        async def failing_handler(env: EventEnvelope) -> None:
            raise RuntimeError("Handler failed")

        registry = ConsumerRegistry()
        registry.register(failing_handler)

        deps = create_test_runner_deps(broker=broker)
        runner = ConsumerRunner(
            registry=registry,
            config=stream_config,
            deps=deps,
            max_retries=0,
        )

        await broker.publish("backend.events", envelope)

        await runner.start()
        await asyncio.sleep(0.15)
        await runner.stop()

        unacked = broker.get_unacked_messages("backend.events", "test-group")
        assert len(unacked) == 1

    async def test_runner_multiple_handlers(
        self,
        broker: InMemoryBroker,
        stream_config: StreamConfig,
        envelope: EventEnvelope,
    ) -> None:
        call_order: list[str] = []

        async def handler_a(env: EventEnvelope) -> None:
            call_order.append("a")

        async def handler_b(env: EventEnvelope) -> None:
            call_order.append("b")

        registry = ConsumerRegistry()
        registry.register(handler_a)
        registry.register(handler_b)

        deps = create_test_runner_deps(broker=broker)
        runner = ConsumerRunner(
            registry=registry,
            config=stream_config,
            deps=deps,
        )

        await broker.publish("backend.events", envelope)

        await runner.start()
        await asyncio.sleep(0.15)
        await runner.stop()

        assert call_order == ["a", "b"]

    async def test_runner_respects_event_filter(
        self,
        broker: InMemoryBroker,
        stream_config: StreamConfig,
    ) -> None:
        handled: list[EventEnvelope] = []

        async def handler(env: EventEnvelope) -> None:
            handled.append(env)

        registry = ConsumerRegistry()
        registry.register(
            handler,
            event_filter={EventName.TRANSPORT_CONNECTORS_CHANGED},
        )

        deps = create_test_runner_deps(broker=broker)
        runner = ConsumerRunner(
            registry=registry,
            config=stream_config,
            deps=deps,
        )

        await broker.publish(
            "backend.events",
            EventEnvelope(
                event_name=EventName.TRANSPORT_CONNECTORS_CHANGED,
                event_version=1,
                producer=Producer.BACKEND,
                dedupe_key="filtered-in",
            ),
        )

        await runner.start()
        await asyncio.sleep(0.15)
        await runner.stop()

        assert len(handled) == 1

    async def test_runner_stop_is_idempotent(
        self,
        broker: InMemoryBroker,
        stream_config: StreamConfig,
    ) -> None:
        registry = ConsumerRegistry()
        registry.register(lambda env: None)  # type: ignore
        deps = create_test_runner_deps(broker=broker)
        runner = ConsumerRunner(
            registry=registry,
            config=stream_config,
            deps=deps,
        )

        await runner.stop()
        await runner.stop()
