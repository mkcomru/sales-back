from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping

from fastapi.responses import JSONResponse

from common.models.transport import TransportDeliveryPayload


class BaseTransportDeliveryService(ABC):
    """Contract for outbound delivery handlers in transport modules."""

    @abstractmethod
    async def handle(
        self,
        *,
        payload: TransportDeliveryPayload,
        headers: Mapping[str, str],
    ) -> JSONResponse: ...

    def resolve_recipient(self, payload: TransportDeliveryPayload) -> str:
        """Extract recipient identifier from payload metadata.

        Checks metadata.chat_id, then metadata.extra.chat_id,
        falling back to conversation_id if neither is present.
        """
        meta = payload.metadata or {}
        extra = meta.get("extra")
        extra_meta = dict(extra) if isinstance(extra, Mapping) else {}
        chat_id = meta.get("chat_id") or extra_meta.get("chat_id")
        return str(chat_id) if chat_id else payload.conversation_id
