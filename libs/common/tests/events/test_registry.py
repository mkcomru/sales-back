"""Tests for consumer registry."""

from common.events.envelope import EventEnvelope, EventName
from common.events.registry import ConsumerRegistry


async def dummy_handler(envelope: EventEnvelope) -> None:
    pass


async def another_handler(envelope: EventEnvelope) -> None:
    pass


class TestConsumerRegistry:
    def test_register_handler(self) -> None:
        registry = ConsumerRegistry()
        registry.register(dummy_handler)

        assert registry.has_handlers()
        assert dummy_handler in registry.get_all_handlers()

    def test_register_multiple_handlers(self) -> None:
        registry = ConsumerRegistry()
        registry.register(dummy_handler)
        registry.register(another_handler)

        handlers = registry.get_all_handlers()
        assert len(handlers) == 2
        assert dummy_handler in handlers
        assert another_handler in handlers

    def test_get_handlers_for_event_no_filter(self) -> None:
        registry = ConsumerRegistry()
        registry.register(dummy_handler)

        handlers = registry.get_handlers_for_event(EventName.TRANSPORT_CONNECTORS_CHANGED)
        assert dummy_handler in handlers

    def test_get_handlers_for_event_with_filter(self) -> None:
        registry = ConsumerRegistry()
        registry.register(
            dummy_handler,
            event_filter={EventName.TRANSPORT_CONNECTORS_CHANGED},
        )
        registry.register(another_handler)

        handlers = registry.get_handlers_for_event(EventName.TRANSPORT_CONNECTORS_CHANGED)
        assert dummy_handler in handlers
        assert another_handler in handlers

    def test_has_handlers_empty(self) -> None:
        registry = ConsumerRegistry()

        assert not registry.has_handlers()

    def test_event_filter_excludes_non_matching(self) -> None:
        registry = ConsumerRegistry()
        registry.register(
            dummy_handler,
            event_filter={EventName.TRANSPORT_CONNECTORS_CHANGED},
        )

        handlers = registry.get_handlers_for_event(EventName.TRANSPORT_CONNECTORS_CHANGED)
        assert dummy_handler in handlers
