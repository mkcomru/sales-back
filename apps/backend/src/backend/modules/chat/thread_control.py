"""Thread control orchestration — applies control actions and notifies via WebSocket."""

from __future__ import annotations

from datetime import UTC, datetime

from src.backend.modules.chat.models import AssistantMode, ChatMessageRole, ChatMessageStatus, ChatMessageType
from src.backend.modules.chat.models import ThreadState as DBThreadState
from src.backend.modules.chat.schemas import AssistantMode as SchemaAssistantMode
from src.backend.modules.chat.schemas import ThreadControlAction, ThreadControlResponse, ThreadState
from src.backend.modules.chat.service import ChatService
from src.backend.modules.chat.websocket import WebSocketManager


async def apply_thread_control(
    thread_id: str,
    action: ThreadControlAction,
    issued_by: str,
    chat_service: ChatService,
    ws_manager: WebSocketManager,
    *,
    updated_by: str | None = None,
) -> ThreadControlResponse:
    """Apply control action to a thread and broadcast via WebSocket."""
    match action:
        case ThreadControlAction.HANDOFF_TO_OPERATOR:
            new_state = DBThreadState.WAITING_MANAGER
            mode = AssistantMode.INACTIVE
            reason = "Manual handoff to operator"
        case ThreadControlAction.STOP_ASSISTANT:
            new_state = DBThreadState.WAITING_MANAGER
            mode = AssistantMode.INACTIVE
            reason = "Assistant manually stopped"
        case ThreadControlAction.RESUME_ASSISTANT:
            new_state = DBThreadState.ACTIVE
            mode = AssistantMode.ACTIVE
            reason = "Assistant manually resumed"
        case ThreadControlAction.RETURN_TO_ASSISTANT:
            new_state = DBThreadState.ACTIVE
            mode = AssistantMode.ACTIVE
            reason = "Returned to assistant from manual control"
        case _:
            new_state = DBThreadState.ACTIVE
            mode = AssistantMode.ACTIVE
            reason = "Control action applied"

    thread = await chat_service.update_thread_state(
        thread_id=thread_id,
        state=new_state,
        reason=reason,
    )
    await chat_service.control_thread_mode(
        thread_id=thread_id,
        mode=mode,
        reason=reason,
    )

    response = ThreadControlResponse(
        thread_id=thread_id,
        action=action,
        state=ThreadState(thread.state.value),
        assistant_mode=SchemaAssistantMode(mode.value),
        issued_by=issued_by,
        effective_at=datetime.now(UTC),
        metadata={"action_source": "ui"},
    )

    assignee_info = await chat_service.build_assignee_info_from_order(thread)
    assignee_payload = assignee_info.model_dump(mode="json") if assignee_info else None

    await ws_manager.notify_control(
        thread.company_id,
        thread_id,
        {
            "action": action.value,
            "state": response.state.value,
            "assistant_mode": mode.value,
            "issued_by": issued_by,
        },
        assistant_mode=mode.value,
        thread_state=response.state.value,
        list_extra={"assignee": assignee_payload},
    )

    if action == ThreadControlAction.STOP_ASSISTANT and updated_by:
        content = f"Диалог перехвачен менеджером\n\nКто: {updated_by}"
        sys_msg = await chat_service.create_message(
            thread_id=thread_id,
            role=ChatMessageRole.SYSTEM,
            content=content,
            status=ChatMessageStatus.SENT,
            message_type=ChatMessageType.SYSTEM_EVENT,
            metadata={"event_type": "manager_intercept", "updated_by": updated_by},
        )
        await ws_manager.notify_system_message(thread_id, sys_msg)

    return response
