"""Router tests for message routing endpoints."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from common.models import ConnectorContext, MessageRole

from src.backend.modules.chat.models import AssistantMode, ChatMessageRole, ChatMessageStatus, Thread, ThreadState
from src.backend.modules.prompts.models import AgentType, Prompt
from src.backend.modules.transport.models import Connector, ConnectorApiKey, ConnectorType


def _mock_chat_service_for_outbound() -> AsyncMock:
    """ChatService mock with create_message + get_thread_by_id wired for outbound tests."""
    msg_counter = 0

    async def fake_create_message(**kwargs):
        nonlocal msg_counter
        msg_counter += 1
        m = MagicMock()
        m.message_id = f"test-msg-{msg_counter}"
        m.content = kwargs["content"]
        m.transcription = kwargs.get("transcription")
        m.role = ChatMessageRole.ASSISTANT
        m.status = ChatMessageStatus.SENT
        m.created_at = datetime.now(UTC)
        m.delivered_at = kwargs["delivered_at"]
        m.metadata = kwargs.get("metadata") or {}
        m.attachments = []
        m.artifact_ids = []
        m.reply_to = None
        return m

    mock_thread = MagicMock()
    mock_thread.state = MagicMock(value="active")
    mock_thread.assistant_mode = MagicMock(value="active")

    mock_chat_service = AsyncMock()
    mock_chat_service.create_message = AsyncMock(side_effect=fake_create_message)
    mock_chat_service.get_thread_by_id = AsyncMock(return_value=mock_thread)
    return mock_chat_service


class TestInboundMessageRouter:
    """Tests for POST /api/v1/messages/inbound endpoint."""

    async def test_inbound_with_service_key_and_connector_id(
        self,
        api_client: httpx.AsyncClient,
        service_headers,
        company_factory,
    ):
        """Test inbound message with X-Service-Key and X-Connector-Id headers."""
        company = await company_factory()
        from src.backend.modules.billing.models import CompanyBalance

        await CompanyBalance.create(company_id=company.id, balance=10)
        await Prompt.create(agent_type=AgentType.AGENT, content="Test prompt")
        await Connector.create(
            connector_id="tg-bot-123",
            company=company,
            type=ConnectorType.TELEGRAM,
            channel_type="telegram",
            display_name="Test Bot",
            managed=True,
            config={"bot_token": "token123"},
            enabled=True,
        )

        envelope = {
            "conversation_id": "conv-123",
            "user_id": "user-123",
            "text": "Hello",
            "ts": 1234567890.0,
        }

        headers = {
            **service_headers,
            "X-Connector-Id": "tg-bot-123",
        }

        from src.backend.modules.core.dependencies import get_sales_agent_client

        mock_client_instance = AsyncMock()
        mock_client_instance.forward_inbound = AsyncMock()

        api_client._transport.app.dependency_overrides[get_sales_agent_client] = lambda: mock_client_instance

        try:
            response = await api_client.post(
                "/api/v1/messages/inbound",
                json=envelope,
                headers=headers,
            )

            assert response.status_code == 202
            data = response.json()
            assert data["status"] == "accepted"

            # Verify Sales Agent client was called
            assert mock_client_instance.forward_inbound.called
            call_args = mock_client_instance.forward_inbound.call_args
            request = call_args[0][0]
            assert request.qualification_workflow is not None
            assert request.qualification_examples is not None
        finally:
            # Clean up override
            api_client._transport.app.dependency_overrides.pop(get_sales_agent_client, None)

    async def test_inbound_customer_assistant_inactive_skips_forward_inbound(
        self,
        api_client: httpx.AsyncClient,
        service_headers,
        company_factory,
    ):
        """Customer message with assistant inactive is persisted but not forwarded to Sales Agent."""
        company = await company_factory()
        from src.backend.modules.billing.models import CompanyBalance
        from src.backend.modules.chat.models import Customer

        await CompanyBalance.create(company_id=company.id, balance=10)
        await Prompt.create(agent_type=AgentType.AGENT, content="Test prompt")

        customer = await Customer.create(
            user_id="user-ai-off-1",
            company_id=company.id,
            meta={},
        )
        await Thread.create(
            thread_id="thread-ai-off-1",
            customer_id=customer.id,
            company_id=company.id,
            channel_type="telegram",
            conversation_id="conv-ai-off-1",
            state=ThreadState.ACTIVE,
            assistant_mode=AssistantMode.INACTIVE,
        )

        await Connector.create(
            connector_id="tg-ai-off-1",
            company=company,
            type=ConnectorType.TELEGRAM,
            channel_type="telegram",
            display_name="AI Off Bot",
            managed=True,
            config={"bot_token": "token123"},
            enabled=True,
        )

        envelope = {
            "conversation_id": "conv-ai-off-1",
            "user_id": "user-ai-off-1",
            "text": "Hello while AI off",
            "ts": 1234567890.0,
            "role": "user",
        }

        headers = {**service_headers, "X-Connector-Id": "tg-ai-off-1"}

        from src.backend.modules.core.dependencies import get_sales_agent_client

        mock_client_instance = AsyncMock()
        mock_client_instance.forward_inbound = AsyncMock()

        api_client._transport.app.dependency_overrides[get_sales_agent_client] = lambda: mock_client_instance

        try:
            response = await api_client.post("/api/v1/messages/inbound", json=envelope, headers=headers)
            assert response.status_code == 202
            assert not mock_client_instance.forward_inbound.called
        finally:
            api_client._transport.app.dependency_overrides.pop(get_sales_agent_client, None)

    async def test_inbound_manager_message_disables_assistant_skips_forward(
        self,
        api_client: httpx.AsyncClient,
        service_headers,
        company_factory,
    ):
        """Manager-role ingress turns assistant off and does not forward to Sales Agent."""
        company = await company_factory()
        from src.backend.modules.billing.models import CompanyBalance
        from src.backend.modules.chat.models import Customer

        await CompanyBalance.create(company_id=company.id, balance=10)
        await Prompt.create(agent_type=AgentType.AGENT, content="Test prompt")

        customer = await Customer.create(
            user_id="user-mgr-ingress-1",
            company_id=company.id,
            meta={},
        )
        thread = await Thread.create(
            thread_id="thread-mgr-ingress-1",
            customer_id=customer.id,
            company_id=company.id,
            channel_type="telegram",
            conversation_id="conv-mgr-ingress-1",
            state=ThreadState.ACTIVE,
            assistant_mode=AssistantMode.ACTIVE,
        )

        await Connector.create(
            connector_id="tg-mgr-ingress-1",
            company=company,
            type=ConnectorType.TELEGRAM,
            channel_type="telegram",
            display_name="Mgr Ingress Bot",
            managed=True,
            config={"bot_token": "token123"},
            enabled=True,
        )

        envelope = {
            "conversation_id": "conv-mgr-ingress-1",
            "user_id": "user-mgr-ingress-1",
            "text": "Manager says hi",
            "ts": 1234567890.0,
            "role": MessageRole.MANAGER.value,
        }

        headers = {**service_headers, "X-Connector-Id": "tg-mgr-ingress-1"}

        from src.backend.modules.core.dependencies import get_sales_agent_client

        mock_client_instance = AsyncMock()
        mock_client_instance.forward_inbound = AsyncMock()

        api_client._transport.app.dependency_overrides[get_sales_agent_client] = lambda: mock_client_instance

        try:
            response = await api_client.post("/api/v1/messages/inbound", json=envelope, headers=headers)
            assert response.status_code == 202
            assert not mock_client_instance.forward_inbound.called

            await thread.refresh_from_db()
            assert thread.assistant_mode == AssistantMode.INACTIVE
        finally:
            api_client._transport.app.dependency_overrides.pop(get_sales_agent_client, None)

    async def test_inbound_with_bearer_token(
        self,
        api_client: httpx.AsyncClient,
        company_factory,
    ):
        """Test inbound message with Bearer token for custom connector."""
        company = await company_factory()
        from src.backend.modules.billing.models import CompanyBalance

        await CompanyBalance.create(company_id=company.id, balance=10)
        await Prompt.get_or_create(agent_type=AgentType.AGENT, defaults={"content": "Test prompt"})
        connector = await Connector.create(
            connector_id="custom-connector",
            company=company,
            type=ConnectorType.CUSTOM,
            channel_type="custom-channel",
            display_name="Custom Connector",
            managed=False,
            config={},
            enabled=True,
        )

        # Create API key for custom connector
        api_key_hash = "hashed_key_123"  # pragma: allowlist secret
        await ConnectorApiKey.create(
            connector=connector,
            key_hash=api_key_hash,
            display_name="Test Key",
        )

        envelope = {
            "conversation_id": "conv-456",
            "user_id": "user-456",
            "text": "Hello from custom",
            "ts": 1234567890.0,
        }

        from src.backend.modules.core.dependencies import get_sales_agent_client

        mock_client_instance = AsyncMock()
        mock_client_instance.forward_inbound = AsyncMock()

        # Mock validate_bearer_token
        mock_context = ConnectorContext(
            connector_id="custom-connector",
            company_id=company.id,
            type="custom",
            channel_type="custom-channel",
            debounce={"window_seconds": 45, "storage_key_template": "{connector_id}:{conversation_id}"},
        )

        with patch(
            "src.backend.modules.messages.routers.validate_bearer_token",
            new_callable=AsyncMock,
            return_value=mock_context,
        ):
            api_client._transport.app.dependency_overrides[get_sales_agent_client] = lambda: mock_client_instance

            try:
                response = await api_client.post(
                    "/api/v1/messages/inbound",
                    json=envelope,
                    headers={"Authorization": "Bearer sk_test_key"},  # pragma: allowlist secret
                )

                assert response.status_code == 202
                data = response.json()
                assert data["status"] == "accepted"
                assert mock_client_instance.forward_inbound.called
                call_args = mock_client_instance.forward_inbound.call_args
                request = call_args[0][0]
                assert request.qualification_workflow is not None
                assert request.qualification_examples is not None
            finally:
                api_client._transport.app.dependency_overrides.pop(get_sales_agent_client, None)

    async def test_inbound_missing_auth(self, api_client: httpx.AsyncClient):
        """Test inbound message without authentication."""
        envelope = {
            "conversation_id": "conv-123",
            "user_id": "user-123",
            "text": "Hello",
            "ts": 1234567890.0,
        }

        response = await api_client.post("/api/v1/messages/inbound", json=envelope)

        assert response.status_code == 401
        data = response.json()
        assert data["detail"]["error"] == "missing_token"

    async def test_inbound_invalid_service_key(
        self,
        api_client: httpx.AsyncClient,
        company_factory,
    ):
        """Test inbound message with invalid service key."""
        company = await company_factory()
        await Connector.create(
            connector_id="tg-bot-123",
            company=company,
            type=ConnectorType.TELEGRAM,
            channel_type="telegram",
            display_name="Test Bot",
            managed=True,
            config={"bot_token": "token123"},
            enabled=True,
        )

        envelope = {
            "conversation_id": "conv-123",
            "user_id": "user-123",
            "text": "Hello",
            "ts": 1234567890.0,
        }

        headers = {
            "X-Service-Key": "invalid-key",
            "X-Connector-Id": "tg-bot-123",
        }

        response = await api_client.post("/api/v1/messages/inbound", json=envelope, headers=headers)

        assert response.status_code == 401

    async def test_inbound_disabled_connector(
        self,
        api_client: httpx.AsyncClient,
        service_headers,
        company_factory,
    ):
        """Test inbound message to disabled connector."""
        company = await company_factory()
        await Connector.create(
            connector_id="disabled-bot",
            company=company,
            type=ConnectorType.TELEGRAM,
            channel_type="telegram",
            display_name="Disabled Bot",
            managed=True,
            config={"bot_token": "token123"},
            enabled=False,  # Disabled
        )

        envelope = {
            "conversation_id": "conv-123",
            "user_id": "user-123",
            "text": "Hello",
            "ts": 1234567890.0,
        }

        headers = {
            **service_headers,
            "X-Connector-Id": "disabled-bot",
        }

        response = await api_client.post("/api/v1/messages/inbound", json=envelope, headers=headers)

        assert response.status_code == 403
        data = response.json()
        assert data["detail"]["error"] == "connector_disabled"

    async def test_inbound_nonexistent_connector(
        self,
        api_client: httpx.AsyncClient,
        service_headers,
    ):
        """Test inbound message with non-existent connector ID."""
        envelope = {
            "conversation_id": "conv-123",
            "user_id": "user-123",
            "text": "Hello",
            "ts": 1234567890.0,
        }

        headers = {
            **service_headers,
            "X-Connector-Id": "nonexistent-bot",
        }

        response = await api_client.post("/api/v1/messages/inbound", json=envelope, headers=headers)

        assert response.status_code == 403

    async def test_inbound_sales_agent_unavailable(
        self,
        api_client: httpx.AsyncClient,
        service_headers,
        company_factory,
    ):
        """Test inbound message when Sales Agent is unavailable."""
        company = await company_factory()
        from src.backend.modules.billing.models import CompanyBalance

        await CompanyBalance.create(company_id=company.id, balance=10)
        await Prompt.create(agent_type=AgentType.AGENT, content="Test prompt")
        await Connector.create(
            connector_id="tg-bot-123",
            company=company,
            type=ConnectorType.TELEGRAM,
            channel_type="telegram",
            display_name="Test Bot",
            managed=True,
            config={"bot_token": "token123"},
            enabled=True,
        )

        envelope = {
            "conversation_id": "conv-123",
            "user_id": "user-123",
            "text": "Hello",
            "ts": 1234567890.0,
        }

        headers = {
            **service_headers,
            "X-Connector-Id": "tg-bot-123",
        }

        from src.backend.modules.core.dependencies import get_sales_agent_client
        from src.backend.modules.messages.sales_agent_client import SalesAgentClientError

        mock_client_instance = AsyncMock()
        mock_client_instance.forward_inbound = AsyncMock(side_effect=SalesAgentClientError("Connection failed"))

        api_client._transport.app.dependency_overrides[get_sales_agent_client] = lambda: mock_client_instance

        try:
            response = await api_client.post("/api/v1/messages/inbound", json=envelope, headers=headers)

            assert response.status_code == 503
            data = response.json()
            assert data["detail"]["error"] == "service_unavailable"
        finally:
            api_client._transport.app.dependency_overrides.pop(get_sales_agent_client, None)


class TestOutboundMessageRouter:
    """Tests for POST /api/v1/internal/messages/outbound endpoint."""

    async def test_outbound_success_telegram(
        self,
        api_client: httpx.AsyncClient,
        service_headers,
        company_factory,
    ):
        """Test successful outbound message routing to Telegram transport."""
        company = await company_factory()
        await Connector.create(
            connector_id="tg-bot-outbound",
            company=company,
            type=ConnectorType.TELEGRAM,
            channel_type="telegram",
            display_name="Outbound Bot",
            managed=True,
            config={"bot_token": "token123"},
            enabled=True,
        )

        payload = {
            "connector_id": "tg-bot-outbound",
            "conversation_id": "conv-789",
            "thread_id": "thread-123",
            "correlation_id": "corr-123",
            "replies": ["Hello!", "How can I help?"],
            "metadata": {"user_id": "user-789"},
            "stage_id": "QUALIFIED",
        }

        from src.backend.modules.chat.dependencies import chat_service
        from src.backend.modules.messages.dependencies import transport_client

        mock_client_instance = AsyncMock()
        mock_client_instance.deliver = AsyncMock()

        mock_chat_service = _mock_chat_service_for_outbound()

        api_client._transport.app.dependency_overrides[transport_client] = lambda: mock_client_instance
        api_client._transport.app.dependency_overrides[chat_service] = lambda: mock_chat_service

        try:
            response = await api_client.post(
                "/api/v1/internal/messages/outbound",
                json=payload,
                headers=service_headers,
            )

            assert response.status_code == 202
            data = response.json()
            assert data["status"] == "accepted"

            # Verify chat_service.create_message was called for each reply
            assert mock_chat_service.create_message.call_count == 2

            # Verify transport client was called
            assert mock_client_instance.deliver.called
            call_args = mock_client_instance.deliver.call_args
            assert call_args.kwargs["connector"].connector_id == "tg-bot-outbound"
            assert call_args.kwargs["connector"].type.value == "telegram"
            assert call_args.kwargs["payload"]["replies"] == ["Hello!", "How can I help?"]
        finally:
            api_client._transport.app.dependency_overrides.pop(transport_client, None)
            api_client._transport.app.dependency_overrides.pop(chat_service, None)

    async def test_outbound_success_wappi(
        self,
        api_client: httpx.AsyncClient,
        service_headers,
        company_factory,
    ):
        """Test successful outbound message routing to Wappi transport."""
        company = await company_factory()
        await Connector.create(
            connector_id="wappi-outbound",
            company=company,
            type=ConnectorType.WAPPI,
            channel_type="whatsapp",
            display_name="Wappi Bot",
            managed=True,
            config={"wappi_token": "token123"},
            enabled=True,
        )

        payload = {
            "connector_id": "wappi-outbound",
            "conversation_id": "conv-wappi",
            "thread_id": "thread-wappi",
            "correlation_id": "corr-wappi",
            "replies": ["WhatsApp message"],
            "metadata": {},
        }

        from src.backend.modules.chat.dependencies import chat_service
        from src.backend.modules.messages.dependencies import transport_client

        mock_client_instance = AsyncMock()
        mock_client_instance.deliver = AsyncMock()

        mock_chat_service = _mock_chat_service_for_outbound()

        api_client._transport.app.dependency_overrides[transport_client] = lambda: mock_client_instance
        api_client._transport.app.dependency_overrides[chat_service] = lambda: mock_chat_service

        try:
            response = await api_client.post(
                "/api/v1/internal/messages/outbound",
                json=payload,
                headers=service_headers,
            )

            assert response.status_code == 202
            assert mock_client_instance.deliver.called
            call_args = mock_client_instance.deliver.call_args
            assert call_args.kwargs["connector"].type.value == "wappi"
        finally:
            api_client._transport.app.dependency_overrides.pop(transport_client, None)
            api_client._transport.app.dependency_overrides.pop(chat_service, None)

    async def test_outbound_with_handoff(
        self,
        api_client: httpx.AsyncClient,
        service_headers,
        company_factory,
    ):
        """Test outbound message with handoff information."""
        company = await company_factory()
        await Connector.create(
            connector_id="tg-handoff",
            company=company,
            type=ConnectorType.TELEGRAM,
            channel_type="telegram",
            display_name="Handoff Bot",
            managed=True,
            config={"bot_token": "token123"},
            enabled=True,
        )

        payload = {
            "connector_id": "tg-handoff",
            "conversation_id": "conv-handoff",
            "thread_id": "thread-handoff",
            "correlation_id": "corr-handoff",
            "replies": ["Transferring to operator"],
            "metadata": {},
            "handoff": {
                "summary": "Customer needs help",
                "reason": "Complex issue",
                "stage": "HANDOFF",
            },
        }

        from src.backend.modules.chat.dependencies import chat_service
        from src.backend.modules.messages.dependencies import transport_client

        mock_client_instance = AsyncMock()
        mock_client_instance.deliver = AsyncMock()

        mock_chat_service = _mock_chat_service_for_outbound()

        api_client._transport.app.dependency_overrides[transport_client] = lambda: mock_client_instance
        api_client._transport.app.dependency_overrides[chat_service] = lambda: mock_chat_service

        try:
            response = await api_client.post(
                "/api/v1/internal/messages/outbound",
                json=payload,
                headers=service_headers,
            )

            assert response.status_code == 202
            call_args = mock_client_instance.deliver.call_args
            assert call_args.kwargs["payload"]["handoff"] == payload["handoff"]
        finally:
            api_client._transport.app.dependency_overrides.pop(transport_client, None)
            api_client._transport.app.dependency_overrides.pop(chat_service, None)

    async def test_outbound_missing_service_key(self, api_client: httpx.AsyncClient):
        """Test outbound message without service key."""
        payload = {
            "connector_id": "tg-bot",
            "conversation_id": "conv-123",
            "thread_id": "thread-123",
            "correlation_id": "corr-123",
            "replies": ["Hello"],
            "metadata": {},
        }

        response = await api_client.post("/api/v1/internal/messages/outbound", json=payload)

        assert response.status_code == 401

    async def test_outbound_connector_not_found(
        self,
        api_client: httpx.AsyncClient,
        service_headers,
    ):
        """Test outbound message with non-existent connector."""
        payload = {
            "connector_id": "nonexistent-bot",
            "conversation_id": "conv-123",
            "thread_id": "thread-123",
            "correlation_id": "corr-123",
            "replies": ["Hello"],
            "metadata": {},
        }

        response = await api_client.post(
            "/api/v1/internal/messages/outbound",
            json=payload,
            headers=service_headers,
        )

        assert response.status_code == 404
        data = response.json()
        assert data["detail"]["error"] == "connector_not_found"

    async def test_outbound_transport_delivery_failed(
        self,
        api_client: httpx.AsyncClient,
        service_headers,
        company_factory,
    ):
        """Test outbound message when transport delivery fails."""
        company = await company_factory()
        await Connector.create(
            connector_id="tg-fail",
            company=company,
            type=ConnectorType.TELEGRAM,
            channel_type="telegram",
            display_name="Fail Bot",
            managed=True,
            config={"bot_token": "token123"},
            enabled=True,
        )

        payload = {
            "connector_id": "tg-fail",
            "conversation_id": "conv-fail",
            "thread_id": "thread-fail",
            "correlation_id": "corr-fail",
            "replies": ["Hello"],
            "metadata": {},
        }

        from src.backend.modules.chat.dependencies import chat_service
        from src.backend.modules.messages.dependencies import transport_client
        from src.backend.modules.messages.transport_client import TransportClientError

        mock_client_instance = AsyncMock()
        mock_client_instance.deliver = AsyncMock(side_effect=TransportClientError("Delivery failed"))

        mock_chat_service = _mock_chat_service_for_outbound()

        api_client._transport.app.dependency_overrides[transport_client] = lambda: mock_client_instance
        api_client._transport.app.dependency_overrides[chat_service] = lambda: mock_chat_service

        try:
            response = await api_client.post(
                "/api/v1/internal/messages/outbound",
                json=payload,
                headers=service_headers,
            )

            assert response.status_code == 500
            data = response.json()
            assert data["detail"]["error"] == "transport_delivery_failed"
        finally:
            api_client._transport.app.dependency_overrides.pop(transport_client, None)
            api_client._transport.app.dependency_overrides.pop(chat_service, None)


class TestInboundMessageBillingIntegration:
    """Integration tests for billing in inbound message router."""

    async def test_inbound_billing_charge_new_thread(
        self,
        api_client: httpx.AsyncClient,
        service_headers,
        company_factory,
    ):
        """Test inbound message charges for new thread when balance is sufficient."""
        company = await company_factory()
        from src.backend.modules.billing.models import CompanyBalance

        await CompanyBalance.create(company_id=company.id, balance=10)
        await Prompt.create(agent_type=AgentType.AGENT, content="Test prompt")

        await Connector.create(
            connector_id="tg-bot-billing",
            company=company,
            type=ConnectorType.TELEGRAM,
            channel_type="telegram",
            display_name="Billing Bot",
            managed=True,
            config={"bot_token": "token123"},
            enabled=True,
        )

        envelope = {
            "conversation_id": "conv-billing-123",
            "user_id": "user-billing-123",
            "text": "Hello",
            "ts": 1234567890.0,
        }

        headers = {
            **service_headers,
            "X-Connector-Id": "tg-bot-billing",
        }

        from src.backend.modules.core.dependencies import get_sales_agent_client

        mock_client_instance = AsyncMock()
        mock_client_instance.forward_inbound = AsyncMock()

        api_client._transport.app.dependency_overrides[get_sales_agent_client] = lambda: mock_client_instance

        try:
            response = await api_client.post("/api/v1/messages/inbound", json=envelope, headers=headers)

            assert response.status_code == 202
            assert mock_client_instance.forward_inbound.called

            balance = await CompanyBalance.get(company_id=company.id)
            assert balance.balance == 9
        finally:
            api_client._transport.app.dependency_overrides.pop(get_sales_agent_client, None)

    async def test_inbound_billing_zero_balance_blocks_new_thread(
        self,
        api_client: httpx.AsyncClient,
        service_headers,
        company_factory,
    ):
        """Test inbound message blocks forwarding when balance is zero for new thread."""
        company = await company_factory()
        from src.backend.modules.billing.models import CompanyBalance

        await CompanyBalance.create(company_id=company.id, balance=0)

        await Connector.create(
            connector_id="tg-bot-zero",
            company=company,
            type=ConnectorType.TELEGRAM,
            channel_type="telegram",
            display_name="Zero Balance Bot",
            managed=True,
            config={"bot_token": "token123"},
            enabled=True,
        )

        envelope = {
            "conversation_id": "conv-zero-123",
            "user_id": "user-zero-123",
            "text": "Hello",
            "ts": 1234567890.0,
        }

        headers = {
            **service_headers,
            "X-Connector-Id": "tg-bot-zero",
        }

        from src.backend.modules.core.dependencies import get_sales_agent_client

        mock_client_instance = AsyncMock()
        mock_client_instance.forward_inbound = AsyncMock()

        api_client._transport.app.dependency_overrides[get_sales_agent_client] = lambda: mock_client_instance

        try:
            response = await api_client.post("/api/v1/messages/inbound", json=envelope, headers=headers)

            assert response.status_code == 202
            assert not mock_client_instance.forward_inbound.called

            from src.backend.modules.chat.models import Thread
            from src.backend.modules.orders.models import Order

            thread = await Thread.filter(company_id=company.id, conversation_id="conv-zero-123").first()
            assert thread is not None
            assert thread.active_order_id is not None

            order = await Order.get(id=thread.active_order_id)
            assert order.billing_status.value == "billing_hold"
        finally:
            api_client._transport.app.dependency_overrides.pop(get_sales_agent_client, None)

    async def test_inbound_billing_existing_thread_billing_hold(
        self,
        api_client: httpx.AsyncClient,
        service_headers,
        company_factory,
    ):
        """Test inbound message blocks forwarding for existing thread with billing_hold status."""
        company = await company_factory()
        from src.backend.modules.billing.models import BillingStatus, CompanyBalance
        from src.backend.modules.chat.models import Customer, Thread, ThreadState

        await CompanyBalance.create(company_id=company.id, balance=0)

        customer = await Customer.create(
            user_id="user-existing-123",
            company_id=company.id,
            meta={},
        )

        from src.backend.modules.orders.repository import OrdersRepository

        orders_repo = OrdersRepository()
        order_number = await orders_repo.get_next_order_number(company.id)
        order = await orders_repo.create_order(
            company_id=company.id,
            customer_id=customer.id,
            order_number=order_number,
            initial_channel="telegram",
        )
        order.billing_status = BillingStatus.BILLING_HOLD
        await order.save(update_fields=["billing_status"])

        await Thread.create(
            thread_id="thread-existing-123",
            customer_id=customer.id,
            company_id=company.id,
            channel_type="telegram",
            conversation_id="conv-existing-123",
            state=ThreadState.ACTIVE,
            assistant_mode=AssistantMode.ACTIVE,
            active_order_id=order.id,
        )

        await Connector.create(
            connector_id="tg-bot-existing",
            company=company,
            type=ConnectorType.TELEGRAM,
            channel_type="telegram",
            display_name="Existing Bot",
            managed=True,
            config={"bot_token": "token123"},
            enabled=True,
        )

        envelope = {
            "conversation_id": "conv-existing-123",
            "user_id": "user-existing-123",
            "text": "Follow-up message",
            "ts": 1234567891.0,
        }

        headers = {
            **service_headers,
            "X-Connector-Id": "tg-bot-existing",
        }

        from src.backend.modules.core.dependencies import get_sales_agent_client

        mock_client_instance = AsyncMock()
        mock_client_instance.forward_inbound = AsyncMock()

        api_client._transport.app.dependency_overrides[get_sales_agent_client] = lambda: mock_client_instance

        try:
            response = await api_client.post("/api/v1/messages/inbound", json=envelope, headers=headers)

            assert response.status_code == 202
            assert not mock_client_instance.forward_inbound.called
        finally:
            api_client._transport.app.dependency_overrides.pop(get_sales_agent_client, None)

    async def test_inbound_billing_existing_thread_zero_balance_check(
        self,
        api_client: httpx.AsyncClient,
        service_headers,
        company_factory,
    ):
        """Test inbound message blocks forwarding for existing thread when balance becomes zero."""
        company = await company_factory()
        from src.backend.modules.billing.models import BillingStatus, CompanyBalance
        from src.backend.modules.chat.models import Customer, Thread, ThreadState

        await CompanyBalance.create(company_id=company.id, balance=0)

        customer = await Customer.create(
            user_id="user-zero-check-123",
            company_id=company.id,
            meta={},
        )

        await Thread.create(
            thread_id="thread-zero-check-123",
            customer_id=customer.id,
            company_id=company.id,
            channel_type="telegram",
            conversation_id="conv-zero-check-123",
            state=ThreadState.ACTIVE,
            assistant_mode=AssistantMode.ACTIVE,
            billing_status=BillingStatus.ACTIVE,
        )

        await Connector.create(
            connector_id="tg-bot-zero-check",
            company=company,
            type=ConnectorType.TELEGRAM,
            channel_type="telegram",
            display_name="Zero Check Bot",
            managed=True,
            config={"bot_token": "token123"},
            enabled=True,
        )

        envelope = {
            "conversation_id": "conv-zero-check-123",
            "user_id": "user-zero-check-123",
            "text": "Message after balance depleted",
            "ts": 1234567892.0,
        }

        headers = {
            **service_headers,
            "X-Connector-Id": "tg-bot-zero-check",
        }

        from src.backend.modules.core.dependencies import get_sales_agent_client

        mock_client_instance = AsyncMock()
        mock_client_instance.forward_inbound = AsyncMock()

        api_client._transport.app.dependency_overrides[get_sales_agent_client] = lambda: mock_client_instance

        try:
            response = await api_client.post("/api/v1/messages/inbound", json=envelope, headers=headers)

            assert response.status_code == 202
            assert not mock_client_instance.forward_inbound.called
        finally:
            api_client._transport.app.dependency_overrides.pop(get_sales_agent_client, None)

    async def test_inbound_billing_idempotent_charge(
        self,
        api_client: httpx.AsyncClient,
        service_headers,
        company_factory,
    ):
        """Test inbound message doesn't charge twice for same thread."""
        company = await company_factory()
        from src.backend.modules.billing.models import CompanyBalance
        from src.backend.modules.chat.models import Customer, Thread, ThreadState

        await CompanyBalance.create(company_id=company.id, balance=10)
        await Prompt.create(agent_type=AgentType.AGENT, content="Test prompt")

        customer = await Customer.create(
            user_id="user-idempotent-123",
            company_id=company.id,
            meta={},
        )

        await Thread.create(
            thread_id="thread-idempotent-123",
            customer_id=customer.id,
            company_id=company.id,
            channel_type="telegram",
            conversation_id="conv-idempotent-123",
            state=ThreadState.ACTIVE,
            assistant_mode=AssistantMode.ACTIVE,
        )

        await Connector.create(
            connector_id="tg-bot-idempotent",
            company=company,
            type=ConnectorType.TELEGRAM,
            channel_type="telegram",
            display_name="Idempotent Bot",
            managed=True,
            config={"bot_token": "token123"},
            enabled=True,
        )

        envelope = {
            "conversation_id": "conv-idempotent-123",
            "user_id": "user-idempotent-123",
            "text": "First message",
            "ts": 1234567893.0,
        }

        headers = {
            **service_headers,
            "X-Connector-Id": "tg-bot-idempotent",
        }

        from src.backend.modules.core.dependencies import get_sales_agent_client

        mock_client_instance = AsyncMock()
        mock_client_instance.forward_inbound = AsyncMock()

        api_client._transport.app.dependency_overrides[get_sales_agent_client] = lambda: mock_client_instance

        try:
            response1 = await api_client.post("/api/v1/messages/inbound", json=envelope, headers=headers)
            assert response1.status_code == 202

            balance_after_first = await CompanyBalance.get(company_id=company.id)
            initial_balance = balance_after_first.balance

            envelope2 = {
                "conversation_id": "conv-idempotent-123",
                "user_id": "user-idempotent-123",
                "text": "Second message",
                "ts": 1234567894.0,
            }

            response2 = await api_client.post("/api/v1/messages/inbound", json=envelope2, headers=headers)
            assert response2.status_code == 202

            balance_after_second = await CompanyBalance.get(company_id=company.id)
            assert balance_after_second.balance == initial_balance
        finally:
            api_client._transport.app.dependency_overrides.pop(get_sales_agent_client, None)
