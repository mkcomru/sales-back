"""Event bus framework for signal-only, API-first event propagation."""

from common.events.broker import EventBroker, ReceivedEvent, StreamConfig
from common.events.codec import decode_envelope, encode_envelope
from common.events.envelope import EventEnvelope, EventName, EventTrace, Producer
from common.events.fastapi import (
    EventingConfigError,
    start_event_consumers,
    stop_event_consumers,
)
from common.events.registry import ConsumerRegistry, EventHandler
from common.events.runner import ConsumerRunner, RunnerDependencies

__all__ = [
    "ConsumerRegistry",
    "ConsumerRunner",
    "EventBroker",
    "EventEnvelope",
    "EventHandler",
    "EventingConfigError",
    "EventName",
    "EventTrace",
    "Producer",
    "ReceivedEvent",
    "RunnerDependencies",
    "StreamConfig",
    "decode_envelope",
    "encode_envelope",
    "start_event_consumers",
    "stop_event_consumers",
]
