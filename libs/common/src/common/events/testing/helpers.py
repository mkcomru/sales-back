"""Test helper functions for event bus testing."""

from typing import Any
from uuid import uuid4

import structlog

from common.events.broker import EventBroker
from common.events.envelope import EventEnvelope, EventName, Producer
from common.events.runner import RunnerDependencies
from common.events.testing.broker import InMemoryBroker
from common.events.testing.clock import FakeClock


def create_test_envelope(
    event_name: EventName = EventName.TRANSPORT_CONNECTORS_CHANGED,
    event_version: int = 1,
    payload: dict[str, Any] | None = None,
    dedupe_key: str | None = None,
) -> EventEnvelope:
    """Create a test event envelope with sensible defaults."""
    return EventEnvelope(
        event_name=event_name,
        event_version=event_version,
        producer=Producer.BACKEND,
        dedupe_key=dedupe_key or f"test-{uuid4().hex[:8]}",
        payload=payload or {},
    )


def create_test_runner_deps(
    broker: EventBroker | None = None,
    clock: FakeClock | None = None,
) -> RunnerDependencies:
    """Create RunnerDependencies with test doubles."""
    fake_clock = clock or FakeClock()
    fake_broker = broker or InMemoryBroker()

    return RunnerDependencies(
        broker=fake_broker,
        clock=fake_clock.now,
        sleep=fake_clock.sleep,
        logger=structlog.get_logger("test"),
    )
