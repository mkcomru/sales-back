"""Tests for internal API endpoints."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import Depends, FastAPI

from common.models import AgentContext, ConnectorContext, InboundEnvelope, InternalInboundRequest

from src.sales_agent.services.debounce import DebounceManager


@pytest.fixture
def mock_debouncer() -> DebounceManager:
    """Create a mock debouncer."""
    debouncer = MagicMock(spec=DebounceManager)
    debouncer.add_message = AsyncMock()
    return debouncer


@pytest.fixture
def fastapi_app(mock_debouncer: DebounceManager) -> FastAPI:
    """Create FastAPI app with internal router."""
    from fastapi import FastAPI

    app = FastAPI()

    # Override the get_debouncer dependency
    def get_debouncer_override() -> DebounceManager:
        return mock_debouncer

    # Create a new router with overridden dependency
    from fastapi import APIRouter

    test_router = APIRouter(prefix="/api/v1/internal/messages", tags=["internal"])

    @test_router.post("/inbound", status_code=202)
    async def internal_inbound_message(
        request: InternalInboundRequest,
        debouncer: DebounceManager = Depends(get_debouncer_override),
    ) -> dict[str, str]:
        """Receive internal inbound message from Backend."""
        from src.sales_agent.api.internal_utils import map_to_incoming_message

        message = map_to_incoming_message(request)
        await debouncer.add_message(message)

        return {"status": "accepted"}

    app.include_router(test_router)
    return app


@pytest.fixture
async def api_client(fastapi_app: FastAPI) -> httpx.AsyncClient:
    """Create test API client."""
    transport = httpx.ASGITransport(app=fastapi_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver", follow_redirects=True) as client:
        yield client


class TestInternalInboundEndpoint:
    """Tests for POST /api/v1/internal/messages/inbound endpoint."""

    async def test_internal_inbound_success(
        self,
        api_client: httpx.AsyncClient,
        mock_debouncer: DebounceManager,
    ):
        """Test successful internal inbound message processing."""
        envelope = InboundEnvelope(
            conversation_id="conv-123",
            user_id="user-123",
            text="Hello",
            ts=1234567890.0,
        )
        context = ConnectorContext(
            connector_id="tg-bot-123",
            company_id=1,
            type="telegram",
            channel_type="telegram",
            debounce={"window_seconds": 45, "storage_key_template": "{connector_id}:{conversation_id}"},
        )
        agent_context = AgentContext(
            prompt_template="",
            company={},
            customer_answers={},
            history=[],
            enabled_tools=[],
        )
        request = InternalInboundRequest(
            envelope=envelope, context=context, thread_id="test-thread-123", agent_context=agent_context
        )

        response = await api_client.post(
            "/api/v1/internal/messages/inbound",
            json=request.model_dump(mode="json"),
        )

        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "accepted"

        # Verify debouncer was called
        assert mock_debouncer.add_message.called

    async def test_internal_inbound_with_audio(
        self,
        api_client: httpx.AsyncClient,
        mock_debouncer: DebounceManager,
    ):
        """Test internal inbound message with audio attachment."""
        envelope = InboundEnvelope(
            conversation_id="conv-456",
            user_id="user-456",
            text=None,
            ts=1234567890.0,
            artifact_ids=["company_2/voice/test_audio.mp3"],
        )
        context = ConnectorContext(
            connector_id="tg-bot-456",
            company_id=2,
            type="telegram",
            channel_type="telegram",
            debounce={"window_seconds": 30, "storage_key_template": "{connector_id}:{conversation_id}"},
        )
        agent_context = AgentContext(
            prompt_template="",
            company={},
            customer_answers={},
            history=[],
            enabled_tools=[],
        )
        request = InternalInboundRequest(
            envelope=envelope, context=context, thread_id="test-thread-123", agent_context=agent_context
        )

        response = await api_client.post(
            "/api/v1/internal/messages/inbound",
            json=request.model_dump(mode="json"),
        )

        assert response.status_code == 202

        # Verify message was added with audio attachment
        call_args = mock_debouncer.add_message.call_args
        message = call_args[0][0]
        assert len(message.attachments) == 1
        assert message.attachments[0]["type"] == "voice"
        assert message.attachments[0]["artifact_id"] == "company_2/voice/test_audio.mp3"
        assert message.attachments[0]["mime"] == "audio/mpeg"

    async def test_internal_inbound_without_auth(self, api_client: httpx.AsyncClient, mock_debouncer: DebounceManager):
        """Test internal inbound message works without auth (currently not protected)."""
        envelope = InboundEnvelope(
            conversation_id="conv-123",
            user_id="user-123",
            text="Hello",
            ts=1234567890.0,
        )
        context = ConnectorContext(
            connector_id="tg-bot-123",
            company_id=1,
            type="telegram",
            channel_type="telegram",
            debounce={"window_seconds": 45, "storage_key_template": "{connector_id}:{conversation_id}"},
        )
        agent_context = AgentContext(
            prompt_template="",
            company={},
            customer_answers={},
            history=[],
            enabled_tools=[],
        )
        request = InternalInboundRequest(
            envelope=envelope, context=context, thread_id="test-thread-123", agent_context=agent_context
        )

        response = await api_client.post(
            "/api/v1/internal/messages/inbound",
            json=request.model_dump(mode="json"),
        )

        # Currently endpoint doesn't require auth
        assert response.status_code == 202

    async def test_internal_inbound_invalid_payload(self, api_client: httpx.AsyncClient):
        """Test internal inbound message with invalid payload."""
        invalid_payload = {
            "envelope": {
                "conversation_id": "conv-123",
                # Missing required fields
            },
            "context": {},
        }

        response = await api_client.post(
            "/api/v1/internal/messages/inbound",
            json=invalid_payload,
        )

        assert response.status_code == 422

    async def test_internal_inbound_storage_key_formatting(
        self,
        api_client: httpx.AsyncClient,
        mock_debouncer: DebounceManager,
    ):
        """Test that storage key is correctly formatted from template."""
        envelope = InboundEnvelope(
            conversation_id="conv-789",
            user_id="user-789",
            text="Test message",
            ts=1234567890.0,
        )
        context = ConnectorContext(
            connector_id="tg-bot-789",
            company_id=3,
            type="telegram",
            channel_type="telegram",
            debounce={
                "window_seconds": 60,
                "storage_key_template": "{connector_id}:{conversation_id}:{user_id}",
            },
        )
        agent_context = AgentContext(
            prompt_template="",
            company={},
            customer_answers={},
            history=[],
            enabled_tools=[],
        )
        request = InternalInboundRequest(
            envelope=envelope, context=context, thread_id="test-thread-123", agent_context=agent_context
        )

        await api_client.post(
            "/api/v1/internal/messages/inbound",
            json=request.model_dump(mode="json"),
        )

        # Verify storage key was formatted correctly
        call_args = mock_debouncer.add_message.call_args
        message = call_args[0][0]
        assert message.storage_key == "tg-bot-789:conv-789:user-789"

    async def test_internal_inbound_metadata_included(
        self,
        api_client: httpx.AsyncClient,
        mock_debouncer: DebounceManager,
    ):
        """Test that connector metadata is included in message."""
        envelope = InboundEnvelope(
            conversation_id="conv-metadata",
            user_id="user-metadata",
            text="Test",
            ts=1234567890.0,
        )
        context = ConnectorContext(
            connector_id="tg-bot-metadata",
            company_id=4,
            type="telegram",
            channel_type="telegram",
            debounce={"window_seconds": 45, "storage_key_template": "{connector_id}:{conversation_id}"},
        )
        agent_context = AgentContext(
            prompt_template="",
            company={},
            customer_answers={},
            history=[],
            enabled_tools=[],
        )
        request = InternalInboundRequest(
            envelope=envelope, context=context, thread_id="test-thread-123", agent_context=agent_context
        )

        await api_client.post(
            "/api/v1/internal/messages/inbound",
            json=request.model_dump(mode="json"),
        )

        # Verify metadata was included
        call_args = mock_debouncer.add_message.call_args
        message = call_args[0][0]
        assert message.metadata["connector_id"] == "tg-bot-metadata"
        assert message.metadata["company_id"] == 4
        assert message.metadata["connector_type"] == "telegram"
        assert message.metadata["channel_type"] == "telegram"
