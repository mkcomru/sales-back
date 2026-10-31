"""Consumer registry for event handler registration."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from common.events.envelope import EventEnvelope, EventName

EventHandler = Callable[[EventEnvelope], Awaitable[None]]


@dataclass
class HandlerRegistration:
    """Registration of a handler with optional event filter."""

    handler: EventHandler
    event_filter: set[EventName] | None = None


class ConsumerRegistry:
    """
    Registry mapping event names to handlers.

    Single-stream design: all events flow through one stream,
    handlers filter by event_name.

    Designed to be inherited by apps for custom registration patterns.
    Each app creates `AppConsumerRegistry(ConsumerRegistry)` to extend.

    Usage:
        registry = ConsumerRegistry()
        registry.register(my_handler, event_filter={EventName.XXX})
        registry.register(another_handler)  # handles all events
    """

    def __init__(self) -> None:
        self._handlers: list[HandlerRegistration] = []

    def register(
        self,
        handler: EventHandler,
        event_filter: set[EventName] | None = None,
    ) -> None:
        """
        Register an event handler.

        Multiple handlers can be registered; they run sequentially.

        Args:
            handler: Async callable that processes EventEnvelope
            event_filter: Optional set of event names to filter; None means all events
        """
        self._handlers.append(
            HandlerRegistration(
                handler=handler,
                event_filter=event_filter,
            )
        )

    def get_handlers_for_event(self, event_name: EventName) -> list[EventHandler]:
        """Return handlers that should process the given event name."""
        result = []
        for reg in self._handlers:
            if reg.event_filter is None or event_name in reg.event_filter:
                result.append(reg.handler)
        return result

    def get_all_handlers(self) -> list[EventHandler]:
        """Return all registered handlers."""
        return [reg.handler for reg in self._handlers]

    def has_handlers(self) -> bool:
        """Check if any handlers are registered."""
        return len(self._handlers) > 0
