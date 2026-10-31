"""Tests for order fields backfill functionality."""

import pytest

from src.backend.modules.chat.models import Customer
from src.backend.modules.fields.models import AnswerType, Field, FieldLevel
from src.backend.modules.orders.models import Order
from src.backend.modules.orders.repository import OrdersRepository


@pytest.mark.asyncio
async def test_ensure_all_order_fields_present_adds_missing_fields(company_factory):
    """Test that _ensure_all_order_fields_present adds missing order-level fields."""
    company = await company_factory()
    repo = OrdersRepository()

    # Create customer
    customer = await Customer.create(
        user_id="test_user_order_fields",
        company_id=company.id,
        customer_fields={},
        quiz_answers={},
        langfuse_sessions={},
        meta={},
    )

    # Create order without order_fields
    order = await Order.create(
        company_id=company.id,
        customer_id=customer.id,
        order_number=1,
        order_fields={},
    )

    # Create order-level field
    await Field.create(
        company=company,
        name="budget",
        question="What is your budget?",
        answer_type=AnswerType.NUMBER,
        level=FieldLevel.ORDER,
        display_name="Budget",
    )

    # Ensure fields are present
    updated = await repo._ensure_all_order_fields_present(order)

    assert updated is True
    assert "budget" in order.order_fields
    assert order.order_fields["budget"] is None


@pytest.mark.asyncio
async def test_ensure_all_order_fields_present_preserves_existing_values(company_factory):
    """Test that _ensure_all_order_fields_present preserves existing order_fields values."""
    company = await company_factory()
    repo = OrdersRepository()

    # Create customer
    customer = await Customer.create(
        user_id="test_user_preserve",
        company_id=company.id,
        customer_fields={},
        quiz_answers={},
        langfuse_sessions={},
        meta={},
    )

    # Create order with existing order_fields
    order = await Order.create(
        company_id=company.id,
        customer_id=customer.id,
        order_number=1,
        order_fields={"budget": 1000},
    )

    # Create order-level field (already exists in order_fields)
    await Field.create(
        company=company,
        name="budget",
        question="What is your budget?",
        answer_type=AnswerType.NUMBER,
        level=FieldLevel.ORDER,
    )

    # Create new order-level field
    await Field.create(
        company=company,
        name="destination",
        question="Where to deliver?",
        answer_type=AnswerType.STRING,
        level=FieldLevel.ORDER,
    )

    # Ensure fields are present
    updated = await repo._ensure_all_order_fields_present(order)

    assert updated is True
    # Existing value should be preserved
    assert order.order_fields["budget"] == 1000
    # New field should be added
    assert "destination" in order.order_fields
    assert order.order_fields["destination"] is None


@pytest.mark.asyncio
async def test_ensure_all_order_fields_present_no_update_when_all_present(company_factory):
    """Test that _ensure_all_order_fields_present returns False when all fields already present."""
    company = await company_factory()
    repo = OrdersRepository()

    # Create customer
    customer = await Customer.create(
        user_id="test_user_no_update",
        company_id=company.id,
        customer_fields={},
        quiz_answers={},
        langfuse_sessions={},
        meta={},
    )

    # Create order-level field
    await Field.create(
        company=company,
        name="budget",
        question="What is your budget?",
        answer_type=AnswerType.NUMBER,
        level=FieldLevel.ORDER,
    )

    # Create order with all fields already present
    order = await Order.create(
        company_id=company.id,
        customer_id=customer.id,
        order_number=1,
        order_fields={"budget": None},
    )

    # Ensure fields are present
    updated = await repo._ensure_all_order_fields_present(order)

    assert updated is False
    assert "budget" in order.order_fields


@pytest.mark.asyncio
async def test_ensure_all_order_fields_present_only_includes_order_level_fields(company_factory):
    """Test that _ensure_all_order_fields_present only includes order-level fields, not customer-level."""
    company = await company_factory()
    repo = OrdersRepository()

    # Create customer
    customer = await Customer.create(
        user_id="test_user_level_filter",
        company_id=company.id,
        customer_fields={},
        quiz_answers={},
        langfuse_sessions={},
        meta={},
    )

    # Create customer-level field
    await Field.create(
        company=company,
        name="phone",
        question="What is your phone?",
        answer_type=AnswerType.STRING,
        level=FieldLevel.CUSTOMER,
    )

    # Create order-level field
    await Field.create(
        company=company,
        name="budget",
        question="What is your budget?",
        answer_type=AnswerType.NUMBER,
        level=FieldLevel.ORDER,
    )

    # Create order
    order = await Order.create(
        company_id=company.id,
        customer_id=customer.id,
        order_number=1,
        order_fields={},
    )

    # Ensure fields are present
    updated = await repo._ensure_all_order_fields_present(order)

    assert updated is True
    # Should have order-level field
    assert "budget" in order.order_fields
    # Should NOT have customer-level field
    assert "phone" not in order.order_fields
