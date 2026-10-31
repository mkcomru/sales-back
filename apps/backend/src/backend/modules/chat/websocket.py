"""WebSocket connection manager for real-time chat updates."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import structlog
from fastapi import WebSocket

from src.backend.modules.chat.models import ChatMessage
from src.backend.modules.chat.schemas import RealtimeEvent, RealtimeEventType, chat_message_preview_text

log = structlog.get_logger(__name__)


@dataclass
class ConnectionMeta:
    company_id: int
    user_id: int
    role: str
    thread_ids: set[str] = field(default_factory=set)


class WebSocketManager:
    """Manages WebSocket connections for real-time chat updates."""

    def __init__(self) -> None:
        self.company_connections: dict[int, set[WebSocket]] = defaultdict(set)
        self.thread_subscriptions: dict[str, set[WebSocket]] = defaultdict(set)
        self.connection_meta: dict[WebSocket, ConnectionMeta] = {}
        self._lock = asyncio.Lock()

    async def connect_company(self, websocket: WebSocket, company_id: int, user_id: int, role: str) -> None:
        async with self._lock:
            self.company_connections[company_id].add(websocket)
            self.connection_meta[websocket] = ConnectionMeta(
                company_id=company_id,
                user_id=user_id,
                role=role,
            )
        log.info("websocket.company_connected", company_id=company_id, user_id=user_id, role=role)

    async def disconnect_company(self, websocket: WebSocket) -> None:
        async with self._lock:
            meta = self.connection_meta.pop(websocket, None)
            if meta is None:
                return
            self.company_connections[meta.company_id].discard(websocket)
            if not self.company_connections[meta.company_id]:
                del self.company_connections[meta.company_id]
            for thread_id in meta.thread_ids:
                self.thread_subscriptions[thread_id].discard(websocket)
                if not self.thread_subscriptions[thread_id]:
                    del self.thread_subscriptions[thread_id]
        log.info("websocket.company_disconnected", company_id=meta.company_id, user_id=meta.user_id)

    async def subscribe_thread(self, websocket: WebSocket, thread_id: str) -> None:
        async with self._lock:
            meta = self.connection_meta.get(websocket)
            if meta is None:
                raise ValueError("WebSocket is not registered as a company connection")
            self.thread_subscriptions[thread_id].add(websocket)
            meta.thread_ids.add(thread_id)
        log.info("websocket.thread_subscribed", thread_id=thread_id, user_id=meta.user_id)

    async def unsubscribe_thread(self, websocket: WebSocket, thread_id: str) -> None:
        async with self._lock:
            meta = self.connection_meta.get(websocket)
            self.thread_subscriptions[thread_id].discard(websocket)
            if not self.thread_subscriptions[thread_id]:
                del self.thread_subscriptions[thread_id]
            if meta is not None:
                meta.thread_ids.discard(thread_id)
        log.info("websocket.thread_unsubscribed", thread_id=thread_id)

    async def broadcast_to_company(self, company_id: int, event: RealtimeEvent) -> None:
        async with self._lock:
            connections = self.company_connections[company_id].copy()

        if not connections:
            return

        message = event.model_dump(mode="json")
        disconnected: set[WebSocket] = set()

        for connection in connections:
            try:
                await connection.send_json(message)
            except Exception:
                log.warning("websocket.company_broadcast_failed", company_id=company_id)
                disconnected.add(connection)

        if disconnected:
            async with self._lock:
                for ws in disconnected:
                    meta = self.connection_meta.pop(ws, None)
                    self.company_connections[company_id].discard(ws)
                    if meta is not None:
                        for thread_id in meta.thread_ids:
                            self.thread_subscriptions[thread_id].discard(ws)
                            if not self.thread_subscriptions[thread_id]:
                                del self.thread_subscriptions[thread_id]
                if not self.company_connections[company_id]:
                    del self.company_connections[company_id]

    async def broadcast_to_thread(self, thread_id: str, event: RealtimeEvent) -> None:
        async with self._lock:
            connections = self.thread_subscriptions[thread_id].copy()

        if not connections:
            return

        message = event.model_dump(mode="json")
        disconnected: set[WebSocket] = set()

        for connection in connections:
            try:
                await connection.send_json(message)
            except Exception:
                log.warning("websocket.broadcast_failed", thread_id=thread_id)
                disconnected.add(connection)

        if disconnected:
            async with self._lock:
                for ws in disconnected:
                    meta = self.connection_meta.pop(ws, None)
                    if meta is not None:
                        self.company_connections[meta.company_id].discard(ws)
                        for tid in meta.thread_ids:
                            self.thread_subscriptions[tid].discard(ws)
                            if not self.thread_subscriptions[tid]:
                                del self.thread_subscriptions[tid]

    # ── High-level notification methods ────────────────────

    def _event(self, event_type: RealtimeEventType, thread_id: str, payload: dict) -> RealtimeEvent:
        return RealtimeEvent(
            event_id=str(uuid4()),
            event_type=event_type,
            thread_id=thread_id,
            payload=payload,
            emitted_at=datetime.now(UTC),
        )

    @staticmethod
    def _message_payload(msg: ChatMessage) -> dict:
        """Build canonical MESSAGE payload from a ChatMessage ORM instance."""
        return {
            "message_id": msg.message_id,
            "content": msg.content,
            "transcription": msg.transcription,
            "role": msg.role.value,
            "status": msg.status.value,
            "created_at": msg.created_at.isoformat(),
            "delivered_at": msg.delivered_at.isoformat() if msg.delivered_at else None,
            "metadata": msg.metadata,
            "attachments": msg.attachments,
            "artifact_ids": msg.artifact_ids or [],
            "reply_to": msg.reply_to,
        }

    async def notify_message(
        self,
        company_id: int,
        thread_id: str,
        message: ChatMessage,
        *,
        unread_delta: int = 1,
        thread_state: str = "active",
    ) -> None:
        """Broadcast MESSAGE to thread subscribers + THREAD_LIST_UPDATE to company."""
        payload = self._message_payload(message)
        await self.broadcast_to_thread(thread_id, self._event(RealtimeEventType.MESSAGE, thread_id, payload))
        preview = chat_message_preview_text(content=message.content, transcription=message.transcription)[:100]
        await self.broadcast_to_company(
            company_id,
            self._event(
                RealtimeEventType.THREAD_LIST_UPDATE,
                thread_id,
                {
                    "last_message_preview": preview,
                    "last_message_at": message.created_at.isoformat(),
                    "unread_count_delta": unread_delta,
                    "state": thread_state,
                },
            ),
        )

    async def notify_note(self, thread_id: str, message: ChatMessage) -> None:
        """Broadcast NOTE event to thread subscribers."""
        await self.broadcast_to_thread(
            thread_id,
            self._event(
                RealtimeEventType.NOTE,
                thread_id,
                {
                    "action": "note_created",
                    "note_id": message.message_id,
                    "note_content": message.content,
                    "note_created_at": message.created_at.isoformat(),
                    "note_updated_at": message.updated_at.isoformat(),
                    "note_metadata": message.metadata,
                    "note_attachments": message.attachments,
                },
            ),
        )

    async def notify_thread_created(self, company_id: int, thread_id: str, *, channel_type: str, state: str) -> None:
        """Broadcast THREAD_CREATED to all company subscribers."""
        await self.broadcast_to_company(
            company_id,
            self._event(
                RealtimeEventType.THREAD_CREATED,
                thread_id,
                {
                    "thread_id": thread_id,
                    "company_id": company_id,
                    "channel_type": channel_type,
                    "state": state,
                },
            ),
        )

    async def notify_system_message(self, thread_id: str, message: ChatMessage) -> None:
        """Broadcast system MESSAGE event to thread subscribers only (no thread list update)."""
        payload = self._message_payload(message)
        await self.broadcast_to_thread(thread_id, self._event(RealtimeEventType.MESSAGE, thread_id, payload))

    async def notify_thread_updated(self, thread_id: str, payload: dict) -> None:
        """Broadcast THREAD_UPDATED to thread subscribers."""
        await self.broadcast_to_thread(
            thread_id,
            self._event(RealtimeEventType.THREAD_UPDATED, thread_id, payload),
        )

    async def notify_thread_list_update(
        self,
        company_id: int,
        thread_id: str,
        *,
        thread_state: str,
        assistant_mode: str,
        extra: dict[str, Any] | None = None,
    ) -> None:
        list_payload: dict[str, Any] = {
            "state": thread_state,
            "assistant_mode": assistant_mode,
        }
        if extra:
            list_payload.update(extra)
        await self.broadcast_to_company(
            company_id,
            self._event(RealtimeEventType.THREAD_LIST_UPDATE, thread_id, list_payload),
        )

    async def notify_control(
        self,
        company_id: int,
        thread_id: str,
        payload: dict,
        *,
        assistant_mode: str,
        thread_state: str,
        list_extra: dict[str, Any] | None = None,
    ) -> None:
        """Broadcast CONTROL to thread + THREAD_LIST_UPDATE to company.

        ``payload`` is sent as-is inside the CONTROL event so callers can
        include action-specific fields (``reason``, ``issued_by``, etc.).
        """
        await self.broadcast_to_thread(
            thread_id,
            self._event(RealtimeEventType.CONTROL, thread_id, payload),
        )
        await self.notify_thread_list_update(
            company_id,
            thread_id,
            thread_state=thread_state,
            assistant_mode=assistant_mode,
            extra=list_extra,
        )


websocket_manager = WebSocketManager()


def get_websocket_manager() -> WebSocketManager:
    return websocket_manager
