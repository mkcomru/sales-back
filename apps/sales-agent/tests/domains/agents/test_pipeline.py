"""Integration tests for agents pipeline with mocked LLM.

Tests the main message processing flow from incoming message to response,
with LLM calls mocked but full business logic tested.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from common import SalesAgentSettings
from common.models.io import SimpleChat, SimpleMessage, SimpleUser

from src.sales_agent.agents.pipeline import (
    AgentsPipelineResult,
    process_user_message_agents,
)
from src.sales_agent.connectors import ConnectorContext, ConnectorType
from src.sales_agent.core.llm.client import LLMClient
from src.sales_agent.core.telemetry import Tracer
from src.sales_agent.services.backend_client import BackendClient

_COMPANY_SPEC_DICT = {
    "name": "Test Company",
    "fields": [
        {
            "name": "name",
            "type": "text",
            "required": True,
            "category_id": None,
            "product_id": None,
        },
        {
            "name": "phone",
            "type": "text",
            "required": True,
            "category_id": None,
            "product_id": None,
        },
    ],
    "products": [],
    "stages_config": [
        {
            "name": "new",
            "crm_id": "NEW",
            "display": "New",
            "summary": "New lead",
        }
    ],
    "category_rules": [],
    "tools": [],
    "crm_default_stage_id": "PROCESSED",
    "crm_forward_metadata_keys": [],
}


@pytest.fixture
def mock_llm_client() -> MagicMock:
    """Mock LLMClient for testing."""
    client = MagicMock(spec=LLMClient)
    client.chat = AsyncMock()
    client.model = "gpt-4"
    return client


@pytest.fixture
def mock_backend_client() -> AsyncMock:
    """Mock BackendClient for testing."""
    client = AsyncMock(spec=BackendClient)
    client.get_company_spec = AsyncMock(return_value=_COMPANY_SPEC_DICT)
    client.get_customer_profile = AsyncMock(return_value={"customer_fields": {}, "rejected": False})
    client.get_or_create_thread = AsyncMock(
        return_value={
            "thread_id": "test-thread-1",
            "user_id": "123",
            "company_id": 1,
            "channel_type": "telegram",
            "connector_id": "test-connector",
            "conversation_id": "123",
            "stage": "new",
            "assistant_active": True,
        }
    )
    client.get_recent_history = AsyncMock(return_value=[])
    client.get_langfuse_session_id = AsyncMock(return_value=None)
    client.create_langfuse_session = AsyncMock(return_value="test-session-1")
    client.get_manager_handling = AsyncMock(return_value=(False, None))
    return client


@pytest.fixture
def mock_tracer() -> MagicMock:
    """Mock Tracer for testing."""
    tracer = MagicMock(spec=Tracer)
    tracer.start_trace = MagicMock()
    tracer.start_span = MagicMock()
    tracer.update_current_trace = MagicMock()
    tracer.update_current_span = MagicMock()
    tracer.connector_tags = MagicMock(return_value=["test"])
    return tracer


@pytest.fixture
def sample_message() -> SimpleMessage:
    """Sample message for testing."""
    return SimpleMessage(
        text="Привет, меня зовут Иван",
        from_user=SimpleUser(id=123),
        chat=SimpleChat(id=456),
        message_id=1,
        metadata={
            "company_id": 1,
            "conversation_id": "conv-1",
            "channel_type": "telegram",
        },
    )


@pytest.fixture
def connector_context() -> ConnectorContext:
    """Sample connector context."""
    from src.sales_agent.connectors import CONNECTOR_MIN_CAPABILITIES

    return ConnectorContext(
        connector_id="test-connector",
        connector_type=ConnectorType.MESSAGING,
        channel_type="telegram",
        capabilities=CONNECTOR_MIN_CAPABILITIES[ConnectorType.MESSAGING],
        config_snapshot={},
    )


@pytest.mark.asyncio
async def test_pipeline_qualifier_route_new_user(
    settings: SalesAgentSettings,
    mock_llm_client: MagicMock,
    mock_backend_client: AsyncMock,
    mock_tracer: MagicMock,
    sample_message: SimpleMessage,
    connector_context: ConnectorContext,
) -> None:
    """Test pipeline routes new user to Qualifier agent."""
    mock_llm_response = {
        "id": "chat-1",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "Привет, Иван! Как дела?",
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {"total_tokens": 10},
    }
    mock_llm_client.chat.return_value = mock_llm_response

    mock_prompt_service = MagicMock()
    mock_prompt_service.load_prompt = AsyncMock(return_value="Test prompt template")

    from src.sales_agent.services.company_context import set_company_spec

    set_company_spec(_COMPANY_SPEC_DICT)

    sample_message.metadata = {
        **sample_message.metadata,
        "agent_context": {
            "prompt_template": "Test prompt template",
            "company": _COMPANY_SPEC_DICT,
            "customer_answers": {},
            "history": [],
            "enabled_tools": [],
            "langfuse_session_id": None,
        },
    }

    with (
        patch(
            "src.sales_agent.agents.pipeline.humanize_message",
            new_callable=AsyncMock,
            return_value="Привет, Иван! Как дела?",
        ),
    ):
        result = await process_user_message_agents(
            sample_message,
            settings,
            mock_llm_client,
            mock_tracer,
            mock_backend_client,
            connector_context=connector_context,
        )

        assert isinstance(result, AgentsPipelineResult)
        assert result.text == "Привет, Иван! Как дела?"
        assert mock_llm_client.chat.called
        # Note: mock_build_tools was removed as build_qualifier_tools no longer exists


@pytest.mark.asyncio
async def test_pipeline_category_expert_route_with_category(
    settings: SalesAgentSettings,
    mock_llm_client: MagicMock,
    mock_backend_client: AsyncMock,
    mock_tracer: MagicMock,
    sample_message: SimpleMessage,
    connector_context: ConnectorContext,
) -> None:
    """Test pipeline routes to Category Expert when category_id is set."""
    mock_llm_response = {
        "id": "chat-1",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "Вот информация о продукте...",
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {"total_tokens": 10},
    }
    mock_llm_client.chat.return_value = mock_llm_response

    customer_answers = {
        "name": "Иван",
        "phone": "+79001234567",
        "category_id": 1,
    }

    mock_prompt_service = MagicMock()
    mock_prompt_service.load_prompt = AsyncMock(return_value="Test prompt template")

    from src.sales_agent.services.company_context import set_company_spec

    set_company_spec(_COMPANY_SPEC_DICT)

    sample_message.metadata = {
        **sample_message.metadata,
        "agent_context": {
            "prompt_template": "Test prompt template",
            "company": _COMPANY_SPEC_DICT,
            "customer_answers": customer_answers,
            "history": [],
            "enabled_tools": [],
            "langfuse_session_id": None,
        },
    }

    with (
        patch(
            "src.sales_agent.agents.pipeline.humanize_message",
            new_callable=AsyncMock,
            return_value="Вот информация о продукте...",
        ),
    ):
        result = await process_user_message_agents(
            sample_message,
            settings,
            mock_llm_client,
            mock_tracer,
            mock_backend_client,
            connector_context=connector_context,
        )

        assert isinstance(result, AgentsPipelineResult)
        assert result.text == "Вот информация о продукте..."


@pytest.mark.asyncio
async def test_pipeline_qualifier_then_category_expert(
    settings: SalesAgentSettings,
    mock_llm_client: MagicMock,
    mock_backend_client: AsyncMock,
    mock_tracer: MagicMock,
    sample_message: SimpleMessage,
    connector_context: ConnectorContext,
) -> None:
    """Test pipeline routes Qualifier first, then
    Category Expert after category_id set."""
    qualifier_response = {
        "id": "chat-1",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "Спасибо за информацию!",
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "type": "function",
                            "function": {
                                "name": "update_fields",
                                "arguments": '{"updates": {"category_id": 1}}',
                            },
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {"total_tokens": 10},
    }

    category_expert_response = {
        "id": "chat-2",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "Вот подходящие варианты...",
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {"total_tokens": 10},
    }

    mock_llm_client.chat.side_effect = [
        qualifier_response,
        category_expert_response,
    ]

    customer_answers = {
        "name": "Иван",
        "phone": "+79001234567",
    }

    mock_prompt_service = MagicMock()
    mock_prompt_service.load_prompt = AsyncMock(return_value="Test prompt template")

    from src.sales_agent.services.company_context import set_company_spec

    set_company_spec(_COMPANY_SPEC_DICT)

    sample_message.metadata = {
        **sample_message.metadata,
        "agent_context": {
            "prompt_template": "Test prompt template",
            "company": _COMPANY_SPEC_DICT,
            "customer_answers": customer_answers,
            "history": [],
            "enabled_tools": [],
            "langfuse_session_id": None,
        },
    }

    with (
        patch(
            "src.sales_agent.agents.pipeline.humanize_message",
            new_callable=AsyncMock,
            side_effect=lambda text, *args, **kwargs: text,
        ),
    ):
        result = await process_user_message_agents(
            sample_message,
            settings,
            mock_llm_client,
            mock_tracer,
            mock_backend_client,
            connector_context=connector_context,
        )

        assert isinstance(result, AgentsPipelineResult)
        assert "подходящие варианты" in result.text
        assert mock_llm_client.chat.call_count >= 2


@pytest.mark.asyncio
async def test_pipeline_missing_company_id_raises(
    settings: SalesAgentSettings,
    mock_llm_client: MagicMock,
    mock_backend_client: AsyncMock,
    mock_tracer: MagicMock,
    connector_context: ConnectorContext,
) -> None:
    """Test pipeline raises error when company_id is missing."""
    message = SimpleMessage(
        text="Привет",
        from_user=SimpleUser(id=123),
        chat=SimpleChat(id=456),
        message_id=1,
        metadata={},
    )

    with pytest.raises(ValueError, match="company_id is required"):
        await process_user_message_agents(
            message,
            settings,
            mock_llm_client,
            mock_tracer,
            mock_backend_client,
            connector_context=connector_context,
        )


@pytest.mark.asyncio
async def test_pipeline_empty_text_returns_default(
    settings: SalesAgentSettings,
    mock_llm_client: MagicMock,
    mock_backend_client: AsyncMock,
    mock_tracer: MagicMock,
    connector_context: ConnectorContext,
) -> None:
    """Test pipeline returns default message for empty text."""
    message = SimpleMessage(
        text="",
        from_user=SimpleUser(id=123),
        chat=SimpleChat(id=456),
        message_id=1,
        metadata={"company_id": 1},
    )

    result = await process_user_message_agents(
        message,
        settings,
        mock_llm_client,
        mock_tracer,
        mock_backend_client,
        connector_context=connector_context,
    )

    assert result.text == "Пожалуйста, отправьте текстовое сообщение."


@pytest.mark.asyncio
async def test_pipeline_clear_command_resets_profile(
    settings: SalesAgentSettings,
    mock_llm_client: MagicMock,
    mock_backend_client: AsyncMock,
    mock_tracer: MagicMock,
    connector_context: ConnectorContext,
) -> None:
    """Test /clear command resets customer profile."""
    message = SimpleMessage(
        text="/clear",
        from_user=SimpleUser(id=123),
        chat=SimpleChat(id=456),
        message_id=1,
        metadata={"company_id": 1, "conversation_id": "conv-1"},
    )

    message.metadata = {
        **message.metadata,
        "agent_context": {
            "prompt_template": "",
            "company": {},
            "customer_answers": {},
            "history": [],
            "enabled_tools": [],
            "langfuse_session_id": None,
        },
    }

    with (
        patch(
            "src.sales_agent.agents.pipeline.reset_customer_profile",
            new_callable=AsyncMock,
        ) as mock_reset,
        patch(
            "src.sales_agent.agents.pipeline.humanize_message",
            new_callable=AsyncMock,
            return_value="История очищена.",
        ),
    ):
        result = await process_user_message_agents(
            message,
            settings,
            mock_llm_client,
            mock_tracer,
            mock_backend_client,
            connector_context=connector_context,
        )

        assert result.text == "История очищена."
        mock_reset.assert_called_once()
