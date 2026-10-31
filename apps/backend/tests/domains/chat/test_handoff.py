"""Handoff tests: ChatService.handle_handoff with escalate (soft/hard) and assistant_mode."""

import pytest

from src.backend.modules.chat.models import (
    AssistantMode,
    ChatMessage,
    ChatMessageRole,
    ChatMessageStatus,
    ChatMessageType,
    Thread,
    ThreadState,
)


class TestHandleHandoffService:
    """Contract tests for ChatService.handle_handoff (042: stage→escalate, assistant_active→assistant_mode)."""

    @pytest.mark.asyncio
    async def test_handle_handoff_creates_system_message(self, thread: Thread, chat_service):
        service = chat_service

        _updated_thread, system_message = await service.handle_handoff(
            thread_id=thread.thread_id,
            summary="Customer asking about complex technical details",
            reason="complex_question",
        )

        assert system_message is not None
        assert system_message.role == ChatMessageRole.SYSTEM
        assert system_message.type == ChatMessageType.TEXT
        assert system_message.status == ChatMessageStatus.SENT
        assert "Диалог передан менеджеру" in system_message.content
        assert "complex_question" in system_message.content
        assert "Customer asking about complex technical details" in system_message.content

        assert system_message.metadata["event_type"] == "handoff"
        assert system_message.metadata["summary"] == "Customer asking about complex technical details"
        assert system_message.metadata["reason"] == "complex_question"
        assert system_message.metadata["escalate"] is False
        assert system_message.metadata["source"] == "ai_agent"

    @pytest.mark.asyncio
    async def test_handle_handoff_soft_sets_shadowing(self, thread: Thread, chat_service):
        service = chat_service

        updated_thread, _ = await service.handle_handoff(
            thread_id=thread.thread_id,
            summary="User requested human agent",
            reason="user_request",
        )

        assert updated_thread.state == ThreadState.HANDOFF
        assert updated_thread.assistant_mode == AssistantMode.SHADOWING

        db_thread = await Thread.get(id=thread.id)
        assert db_thread.state == ThreadState.HANDOFF
        assert db_thread.assistant_mode == AssistantMode.SHADOWING

    @pytest.mark.asyncio
    async def test_handle_handoff_hard_sets_inactive(self, thread: Thread, chat_service):
        service = chat_service

        updated_thread, system_message = await service.handle_handoff(
            thread_id=thread.thread_id,
            summary="Need manager assistance",
            reason="escalation",
            escalate=True,
        )

        assert system_message.metadata["escalate"] is True
        assert updated_thread.state == ThreadState.HANDOFF
        assert updated_thread.assistant_mode == AssistantMode.INACTIVE

    @pytest.mark.asyncio
    async def test_handle_handoff_thread_not_found(self, chat_service):
        service = chat_service

        with pytest.raises(ValueError, match="Thread nonexistent_thread not found"):
            await service.handle_handoff(
                thread_id="nonexistent_thread",
                summary="Test",
                reason="test",
            )

    @pytest.mark.asyncio
    async def test_handle_handoff_creates_message_in_thread(self, thread: Thread, chat_service):
        service = chat_service

        _, system_message = await service.handle_handoff(
            thread_id=thread.thread_id,
            summary="Complex pricing question",
            reason="needs_expert",
        )

        messages = await ChatMessage.filter(thread=thread).all()
        assert len(messages) == 1
        assert messages[0].id == system_message.id
        assert messages[0].content == system_message.content

    @pytest.mark.asyncio
    async def test_handoff_message_content_formatting(self, thread: Thread, chat_service):
        service = chat_service

        _, message = await service.handle_handoff(
            thread_id=thread.thread_id,
            summary="Customer needs help with installation",
            reason="technical_issue",
        )

        content = message.content
        assert "Диалог передан менеджеру" in content
        assert "Причина: technical_issue" in content
        assert "Содержание разговора: Customer needs help with installation" in content
        assert content.count("\n") >= 2

    @pytest.mark.asyncio
    async def test_handoff_preserves_existing_thread_data(self, thread: Thread, chat_service):
        service = chat_service
        original_channel = thread.channel_type
        original_customer_id = thread.customer_id

        updated_thread, _ = await service.handle_handoff(
            thread_id=thread.thread_id,
            summary="Test",
            reason="test",
        )

        assert updated_thread.channel_type == original_channel
        assert updated_thread.customer_id == original_customer_id
        assert updated_thread.thread_id == thread.thread_id

    @pytest.mark.asyncio
    async def test_multiple_handoffs_create_multiple_messages(self, thread: Thread, chat_service):
        service = chat_service

        await service.handle_handoff(
            thread_id=thread.thread_id,
            summary="First handoff",
            reason="reason_1",
        )

        await service.handle_handoff(
            thread_id=thread.thread_id,
            summary="Second handoff",
            reason="reason_2",
        )

        messages = await ChatMessage.filter(thread=thread, role=ChatMessageRole.SYSTEM).all()
        assert len(messages) == 2
        assert "First handoff" in messages[0].content
        assert "Second handoff" in messages[1].content


class TestNotifyHandoffInternalRouter:
    """POST /internal/chat/threads/{id}/handoff — notify backend about AI handoff."""

    @pytest.mark.asyncio
    async def test_handoff_endpoint_creates_message(self, api_client, service_headers, thread: Thread):
        payload = {
            "summary": "Customer has a complex question about pricing",
            "reason": "complex_question",
        }

        response = await api_client.post(
            f"/api/v1/internal/chat/threads/{thread.thread_id}/handoff",
            json=payload,
            headers=service_headers,
        )

        assert response.status_code == 200
        data = response.json()

        assert data["thread_id"] == thread.thread_id
        assert data["state"] == "handoff"
        assert data["assistant_mode"] == "shadowing"
        assert "message_id" in data
        assert "processed_at" in data

    @pytest.mark.asyncio
    async def test_handoff_endpoint_updates_thread_state(self, api_client, service_headers, thread: Thread):
        assert thread.state == ThreadState.ACTIVE
        assert thread.assistant_mode == AssistantMode.ACTIVE

        payload = {
            "summary": "User requested manager",
            "reason": "user_request",
        }

        response = await api_client.post(
            f"/api/v1/internal/chat/threads/{thread.thread_id}/handoff",
            json=payload,
            headers=service_headers,
        )

        assert response.status_code == 200

        updated_thread = await Thread.get(id=thread.id)
        assert updated_thread.state == ThreadState.HANDOFF
        assert updated_thread.assistant_mode == AssistantMode.SHADOWING

    @pytest.mark.asyncio
    async def test_handoff_endpoint_without_request_body(self, api_client, service_headers, thread: Thread):
        response = await api_client.post(
            f"/api/v1/internal/chat/threads/{thread.thread_id}/handoff",
            headers=service_headers,
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_handoff_endpoint_thread_not_found(self, api_client, service_headers):
        payload = {
            "summary": "Test summary",
            "reason": "test_reason",
        }

        response = await api_client.post(
            "/api/v1/internal/chat/threads/nonexistent_thread/handoff",
            json=payload,
            headers=service_headers,
        )

        assert response.status_code == 404
