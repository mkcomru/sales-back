"""Backend-only event publisher.

Only backend should publish events. This module provides the publisher
wrapper and convenience functions for emitting signal-only events.
"""

from datetime import UTC, datetime

import structlog

from common.events import EventBroker, EventEnvelope, EventName, Producer
from common.events.contracts import (
    ChangeType,
    CompanySpecificationChangedPayloadV1,
    PromptChangedPayloadV1,
    ResourceType,
    TransportConnectorsChangedPayloadV1,
)

log = structlog.get_logger(__name__)

_publisher_instance: "BackendEventPublisher | None" = None


class BackendEventPublisher:
    """
    Backend-only event publisher.

    Wraps the EventBroker to provide type-safe publishing for backend events.
    Publishing is non-blocking: failures are logged but don't affect CRUD operations.
    """

    DEFAULT_STREAM = "backend.events"

    def __init__(
        self,
        broker: EventBroker,
        stream_name: str = DEFAULT_STREAM,
        enabled: bool = True,
    ) -> None:
        self._broker = broker
        self._stream_name = stream_name
        self._enabled = enabled

    async def publish_transport_connectors_changed(
        self,
        change_type: ChangeType,
        resource: ResourceType,
        company_id: int | None = None,
        connector_id: str | None = None,
        correlation_id: str | None = None,
    ) -> None:
        """
        Publish a transport.connectors.changed signal event.

        Non-blocking: failures are logged but don't raise.
        """
        if not self._enabled:
            return

        payload = TransportConnectorsChangedPayloadV1(
            change_type=change_type,
            resource=resource,
            company_id=company_id,
            connector_id=connector_id,
        )

        dedupe_key = self._build_dedupe_key(
            resource=resource,
            change_type=change_type,
            company_id=company_id,
            connector_id=connector_id,
        )

        envelope = EventEnvelope(
            event_name=EventName.TRANSPORT_CONNECTORS_CHANGED,
            event_version=1,
            producer=Producer.BACKEND,
            dedupe_key=dedupe_key,
            payload=payload.model_dump(),
        )

        if correlation_id:
            envelope = envelope.with_trace(correlation_id=correlation_id)

        try:
            message_id = await self._broker.publish(self._stream_name, envelope)
            log.info(
                "event.published",
                stream=self._stream_name,
                event_name=envelope.event_name,
                dedupe_key=dedupe_key,
                message_id=message_id,
            )
        except Exception as exc:
            log.warning(
                "event.publish_failed",
                stream=self._stream_name,
                event_name=envelope.event_name,
                dedupe_key=dedupe_key,
                error=str(exc),
            )

    @staticmethod
    def _build_dedupe_key(
        resource: ResourceType,
        change_type: ChangeType,
        company_id: int | None,
        connector_id: str | None,
    ) -> str:
        """Build a stable dedupe key for idempotency."""
        ts = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
        parts = [resource.value, change_type.value, ts]
        if company_id is not None:
            parts.append(f"c{company_id}")
        if connector_id is not None:
            parts.append(connector_id)
        return ":".join(parts)

    async def publish_prompt_changed(
        self,
        agent_type: str,
        change_type: ChangeType,
        correlation_id: str | None = None,
    ) -> None:
        """Publish prompt.changed signal."""
        if not self._enabled:
            return

        payload = PromptChangedPayloadV1(
            agent_type=agent_type,
            change_type=change_type,
        )

        dedupe_key = ":".join(["prompt", agent_type, change_type.value, datetime.now(UTC).strftime("%Y%m%d%H%M%S")])

        envelope = EventEnvelope(
            event_name=EventName.PROMPT_CHANGED,
            event_version=1,
            producer=Producer.BACKEND,
            dedupe_key=dedupe_key,
            payload=payload.model_dump(),
        )
        if correlation_id:
            envelope = envelope.with_trace(correlation_id=correlation_id)

        try:
            message_id = await self._broker.publish(self._stream_name, envelope)
            log.info(
                "event.published",
                stream=self._stream_name,
                event_name=envelope.event_name,
                dedupe_key=dedupe_key,
                message_id=message_id,
            )
        except Exception as exc:
            log.warning(
                "event.publish_failed",
                stream=self._stream_name,
                event_name=envelope.event_name,
                dedupe_key=dedupe_key,
                error=str(exc),
            )

    async def publish_company_specification_changed(
        self,
        company_id: int,
        change_type: ChangeType,
        correlation_id: str | None = None,
    ) -> None:
        """Publish company.specification.changed signal."""
        if not self._enabled:
            return

        payload = CompanySpecificationChangedPayloadV1(
            company_id=company_id,
            change_type=change_type,
        )

        dedupe_key = ":".join(
            [
                "company_spec",
                str(company_id),
                change_type.value,
                datetime.now(UTC).strftime("%Y%m%d%H%M%S"),
            ]
        )

        envelope = EventEnvelope(
            event_name=EventName.COMPANY_SPECIFICATION_CHANGED,
            event_version=1,
            producer=Producer.BACKEND,
            dedupe_key=dedupe_key,
            payload=payload.model_dump(),
        )
        if correlation_id:
            envelope = envelope.with_trace(correlation_id=correlation_id)

        try:
            message_id = await self._broker.publish(self._stream_name, envelope)
            log.info(
                "event.published",
                stream=self._stream_name,
                event_name=envelope.event_name,
                dedupe_key=dedupe_key,
                message_id=message_id,
            )
        except Exception as exc:
            log.warning(
                "event.publish_failed",
                stream=self._stream_name,
                event_name=envelope.event_name,
                dedupe_key=dedupe_key,
                error=str(exc),
            )

    async def close(self) -> None:
        """Close the underlying broker connection."""
        await self._broker.close()


def get_event_publisher() -> "BackendEventPublisher | None":
    """Get the global event publisher instance (if initialized)."""
    return _publisher_instance


def set_event_publisher(publisher: "BackendEventPublisher | None") -> None:
    """Set the global event publisher instance."""
    global _publisher_instance
    _publisher_instance = publisher


async def publish_transport_connectors_changed(
    change_type: ChangeType,
    resource: ResourceType,
    company_id: int | None = None,
    connector_id: str | None = None,
    correlation_id: str | None = None,
) -> None:
    """
    Convenience function to publish transport.connectors.changed event.

    Uses the global publisher instance. No-op if publisher not initialized.
    """
    publisher = get_event_publisher()
    if publisher is None:
        return

    await publisher.publish_transport_connectors_changed(
        change_type=change_type,
        resource=resource,
        company_id=company_id,
        connector_id=connector_id,
        correlation_id=correlation_id,
    )


async def publish_prompt_changed(
    agent_type: str,
    change_type: ChangeType,
    correlation_id: str | None = None,
) -> None:
    """Convenience: publish prompt.changed via global publisher."""
    publisher = get_event_publisher()
    if publisher is None:
        return
    await publisher.publish_prompt_changed(
        agent_type=agent_type,
        change_type=change_type,
        correlation_id=correlation_id,
    )


async def publish_company_specification_changed(
    company_id: int,
    change_type: ChangeType,
    correlation_id: str | None = None,
) -> None:
    """Convenience: publish company.specification.changed via global publisher."""
    publisher = get_event_publisher()
    if publisher is None:
        return
    await publisher.publish_company_specification_changed(
        company_id=company_id,
        change_type=change_type,
        correlation_id=correlation_id,
    )
