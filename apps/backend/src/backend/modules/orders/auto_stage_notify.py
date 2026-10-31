"""Notify chat when order stage auto-transitions (recalculate_stage)."""

from __future__ import annotations

import structlog

log = structlog.get_logger(__name__)


async def notify_auto_stage_transition(
    order_id: int,
    from_stage_name: str,
    to_stage_name: str,
) -> None:
    """Create system message in thread chat when order auto-transitions stages.

    Similar to manual stage change in update_order router.
    Uses lazy imports to avoid circular dependency OrderService -> ChatService.
    """
    from src.backend.modules.chat.models import Thread
    from src.backend.modules.chat.websocket import get_websocket_manager
    from src.backend.modules.orders.dependencies import order_service

    thread = await Thread.filter(active_order_id=order_id).first()
    if not thread:
        return

    from src.backend.modules.chat.dependencies import chat_service
    from src.backend.modules.chat.models import ChatMessageRole, ChatMessageStatus, ChatMessageType

    svc = chat_service(order_service())
    content = f"Этап изменен: {from_stage_name} → {to_stage_name}\n\nАвтоматически"

    try:
        sys_msg = await svc.create_message(
            thread_id=thread.thread_id,
            role=ChatMessageRole.SYSTEM,
            content=content,
            status=ChatMessageStatus.SENT,
            message_type=ChatMessageType.SYSTEM_EVENT,
            metadata={
                "event_type": "order_stage_change",
                "old_stage": from_stage_name,
                "new_stage": to_stage_name,
                "updated_by": None,
                "trigger": "auto",
            },
        )
        ws = get_websocket_manager()
        await ws.notify_system_message(thread.thread_id, sys_msg)
        log.debug(
            "order.auto_stage_notified",
            order_id=order_id,
            thread_id=thread.thread_id,
            from_stage=from_stage_name,
            to_stage=to_stage_name,
        )
    except Exception as e:
        log.warning(
            "order.auto_stage_notify_failed",
            order_id=order_id,
            thread_id=thread.thread_id,
            error=str(e),
        )
