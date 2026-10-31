"""Tests for ChatService.get_qualification_config."""

from src.backend.modules.chat.models import Thread
from src.backend.modules.chat.service import ChatService
from src.backend.modules.prompt_addon.models import PromptAddon
from src.backend.modules.transport.models import Connector, ConnectorType


async def test_get_qualification_config_from_prompt_addon(company_factory):
    from src.backend.modules.orders.service import OrderService

    service = ChatService(order_service=OrderService())
    company = await company_factory()
    addon = await PromptAddon.create(
        company=company,
        name="Test Addon",
        qualification_workflow="Addon workflow",
        qualification_examples="Addon examples",
    )
    connector = await Connector.create(
        connector_id="test-connector",
        company=company,
        type=ConnectorType.TELEGRAM,
        channel_type="telegram",
        display_name="Test Bot",
        managed=True,
        config={"bot_token": "token"},
        prompt_addon_id=addon.id,
    )
    from src.backend.modules.chat.models import Customer

    customer = await Customer.create(user_id="user-1", company=company)
    thread = await Thread.create(
        thread_id="thread-1",
        customer=customer,
        company=company,
        channel_type="telegram",
        connector_id=connector.connector_id,
    )

    workflow, examples = await service.get_qualification_config(thread)
    assert workflow == "Addon workflow"
    assert examples == "Addon examples"


async def test_get_qualification_config_fallback_to_company(company_factory):
    from src.backend.modules.orders.service import OrderService

    service = ChatService(order_service=OrderService())
    company = await company_factory()
    company.qualification_workflow = "Company workflow"
    company.qualification_examples = "Company examples"
    await company.save()

    from src.backend.modules.chat.models import Customer

    customer = await Customer.create(user_id="user-2", company=company)
    thread = await Thread.create(
        thread_id="thread-2",
        customer=customer,
        company=company,
        channel_type="telegram",
        connector_id=None,
    )

    workflow, examples = await service.get_qualification_config(thread)
    assert workflow == "Company workflow"
    assert examples == "Company examples"


async def test_get_qualification_config_connector_without_addon(company_factory):
    from src.backend.modules.orders.service import OrderService

    service = ChatService(order_service=OrderService())
    company = await company_factory()
    company.qualification_workflow = "Company workflow"
    company.qualification_examples = "Company examples"
    await company.save()

    connector = await Connector.create(
        connector_id="test-connector-2",
        company=company,
        type=ConnectorType.TELEGRAM,
        channel_type="telegram",
        display_name="Test Bot",
        managed=True,
        config={"bot_token": "token"},
        prompt_addon_id=None,
    )
    from src.backend.modules.chat.models import Customer

    customer = await Customer.create(user_id="user-3", company=company)
    thread = await Thread.create(
        thread_id="thread-3",
        customer=customer,
        company=company,
        channel_type="telegram",
        connector_id=connector.connector_id,
    )

    workflow, examples = await service.get_qualification_config(thread)
    assert workflow == "Company workflow"
    assert examples == "Company examples"


async def test_get_qualification_config_connector_not_found(company_factory):
    from src.backend.modules.orders.service import OrderService

    service = ChatService(order_service=OrderService())
    company = await company_factory()
    company.qualification_workflow = "Company workflow"
    company.qualification_examples = "Company examples"
    await company.save()

    from src.backend.modules.chat.models import Customer

    customer = await Customer.create(user_id="user-4", company=company)
    thread = await Thread.create(
        thread_id="thread-4",
        customer=customer,
        company=company,
        channel_type="telegram",
        connector_id="non-existent-connector",
    )

    workflow, examples = await service.get_qualification_config(thread)
    assert workflow == "Company workflow"
    assert examples == "Company examples"
