"""Integration tests for prompt addon in inbound messages."""

from collections.abc import Callable
from contextlib import contextmanager
from typing import Any
from unittest.mock import AsyncMock

import httpx

from src.backend.modules.prompt_addon.models import PromptAddon
from src.backend.modules.prompts.models import AgentType, Prompt
from src.backend.modules.transport.models import Connector, ConnectorType


def _collect_sales_agent_deps() -> list[Callable]:
    """Collect all possible sales agent dependency functions across branches."""
    deps: list[Callable] = []
    try:
        from src.backend.modules.core.dependencies import get_sales_agent_client

        deps.append(get_sales_agent_client)
    except ImportError:
        pass
    try:
        from src.backend.modules.messages.dependencies import sales_agent_client

        deps.append(sales_agent_client)
    except ImportError:
        pass
    return deps


@contextmanager
def _override_sales_agent(app: Any, mock_instance: Any):
    """Override all known sales agent dependency functions with a mock."""
    dep_fns = _collect_sales_agent_deps()
    for fn in dep_fns:
        app.dependency_overrides[fn] = lambda: mock_instance
    try:
        yield
    finally:
        for fn in dep_fns:
            app.dependency_overrides.pop(fn, None)


async def test_inbound_message_uses_prompt_addon_workflow(
    api_client: httpx.AsyncClient,
    service_headers,
    company_factory,
):
    """Test that inbound message uses workflow from prompt addon when connector has one."""
    company = await company_factory()
    company.qualification_workflow = "Company default workflow"
    company.qualification_examples = "Company default examples"
    await company.save()

    from src.backend.modules.billing.models import CompanyBalance

    await CompanyBalance.create(company_id=company.id, balance=10)
    await Prompt.create(agent_type=AgentType.AGENT, content="Test prompt")

    addon = await PromptAddon.create(
        company=company,
        name="Test Addon",
        qualification_workflow="Addon workflow",
        qualification_examples="Addon examples",
    )

    await Connector.create(
        connector_id="tg-bot-addon",
        company=company,
        type=ConnectorType.TELEGRAM,
        channel_type="telegram",
        display_name="Test Bot",
        managed=True,
        config={"bot_token": "token123"},
        enabled=True,
        prompt_addon_id=addon.id,
    )

    envelope = {
        "conversation_id": "conv-addon-123",
        "user_id": "user-addon-123",
        "text": "Hello",
        "ts": 1234567890.0,
    }

    headers = {
        **service_headers,
        "X-Connector-Id": "tg-bot-addon",
    }

    from src.backend.modules.core.dependencies import get_sales_agent_client

    mock_client_instance = AsyncMock()
    mock_client_instance.forward_inbound = AsyncMock()

    api_client._transport.app.dependency_overrides[get_sales_agent_client] = lambda: mock_client_instance

    try:
        response = await api_client.post("/api/v1/messages/inbound", json=envelope, headers=headers)

        assert response.status_code == 202
        assert mock_client_instance.forward_inbound.called

        call_args = mock_client_instance.forward_inbound.call_args
        request = call_args[0][0]
        assert request.qualification_workflow == "Addon workflow"
        assert request.qualification_examples == "Addon examples"
    finally:
        api_client._transport.app.dependency_overrides.pop(get_sales_agent_client, None)


async def test_inbound_message_falls_back_to_company_workflow(
    api_client: httpx.AsyncClient,
    service_headers,
    company_factory,
):
    """Test that inbound message falls back to company workflow when connector has no addon."""
    company = await company_factory()
    company.qualification_workflow = "Company default workflow"
    company.qualification_examples = "Company default examples"
    await company.save()

    from src.backend.modules.billing.models import CompanyBalance

    await CompanyBalance.create(company_id=company.id, balance=10)
    await Prompt.create(agent_type=AgentType.AGENT, content="Test prompt")

    await Connector.create(
        connector_id="tg-bot-no-addon",
        company=company,
        type=ConnectorType.TELEGRAM,
        channel_type="telegram",
        display_name="Test Bot",
        managed=True,
        config={"bot_token": "token123"},
        enabled=True,
        prompt_addon_id=None,
    )

    envelope = {
        "conversation_id": "conv-no-addon-123",
        "user_id": "user-no-addon-123",
        "text": "Hello",
        "ts": 1234567890.0,
    }

    headers = {
        **service_headers,
        "X-Connector-Id": "tg-bot-no-addon",
    }

    from src.backend.modules.core.dependencies import get_sales_agent_client

    mock_client_instance = AsyncMock()
    mock_client_instance.forward_inbound = AsyncMock()

    api_client._transport.app.dependency_overrides[get_sales_agent_client] = lambda: mock_client_instance

    try:
        response = await api_client.post("/api/v1/messages/inbound", json=envelope, headers=headers)

        assert response.status_code == 202
        assert mock_client_instance.forward_inbound.called

        call_args = mock_client_instance.forward_inbound.call_args
        request = call_args[0][0]
        assert request.qualification_workflow == "Company default workflow"
        assert request.qualification_examples == "Company default examples"
    finally:
        api_client._transport.app.dependency_overrides.pop(get_sales_agent_client, None)
