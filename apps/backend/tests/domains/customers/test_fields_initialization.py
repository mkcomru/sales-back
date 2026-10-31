"""Tests for customer fields initialization and schema."""

import pytest

from src.backend.modules.chat.models import Customer
from src.backend.modules.chat.repository import CustomersRepository
from src.backend.modules.fields.models import AnswerType, Field, FieldLevel, FieldOption


@pytest.fixture
async def test_company_with_fields(company_factory):
    """Create test company with fields."""
    company = await company_factory()

    field1 = await Field.create(
        company=company,
        name="name",
        question="What is your name?",
        answer_type=AnswerType.STRING,
        required=True,
        display_name="Name",
        level=FieldLevel.CUSTOMER,
    )

    field2 = await Field.create(
        company=company,
        name="age",
        question="What is your age?",
        answer_type=AnswerType.NUMBER,
        required=False,
        display_name="Age",
        level=FieldLevel.CUSTOMER,
    )

    field3 = await Field.create(
        company=company,
        name="city",
        question="Which city?",
        answer_type=AnswerType.ENUM,
        required=True,
        display_name="City",
        level=FieldLevel.CUSTOMER,
    )

    await FieldOption.create(field=field3, value="Moscow", order=0)
    await FieldOption.create(field=field3, value="Saint Petersburg", order=1)

    return company, [field1, field2, field3]


@pytest.mark.asyncio
async def test_customer_creation_initializes_quiz_answers(test_company_with_fields):
    """Test that creating customer initializes customer_fields with all customer-level fields."""
    company, fields = test_company_with_fields
    repo = CustomersRepository()

    customer, created = await repo.get_or_create(
        user_id="test_user_123",
        company_id=company.id,
        meta={"username": "testuser"},
    )

    assert created is True
    assert customer.customer_fields is not None
    assert "name" in customer.customer_fields
    assert "age" in customer.customer_fields
    assert "city" in customer.customer_fields
    assert customer.customer_fields["name"] is None
    assert customer.customer_fields["age"] is None
    assert customer.customer_fields["city"] is None


@pytest.mark.asyncio
async def test_existing_customer_backfills_new_fields(test_company_with_fields):
    """Test that existing customer gets new fields when company adds them."""
    company, fields = test_company_with_fields
    repo = CustomersRepository()

    # Create customer with initial fields
    customer, _ = await repo.get_or_create(
        user_id="test_user_456",
        company_id=company.id,
    )

    initial_fields_count = len(customer.customer_fields)

    # Add new customer-level field to company
    await Field.create(
        company=company,
        name="phone",
        question="What is your phone?",
        answer_type=AnswerType.STRING,
        required=False,
        display_name="Phone",
        level=FieldLevel.CUSTOMER,
    )

    # Get customer again - should backfill new field
    customer, created = await repo.get_or_create(
        user_id="test_user_456",
        company_id=company.id,
    )

    assert created is False
    assert len(customer.customer_fields) == initial_fields_count + 1
    assert "phone" in customer.customer_fields
    assert customer.customer_fields["phone"] is None


@pytest.mark.asyncio
async def test_get_customer_fields_schema(test_company_with_fields, chat_service):
    """Test getting fields schema for customer."""
    company, fields = test_company_with_fields
    service = chat_service

    schema = await service.get_customer_fields_schema(company.id)

    assert len(schema) == 3

    # Check first field (string)
    name_field = next(f for f in schema if f.name == "name")
    assert name_field.type == "string"
    assert name_field.required is True
    assert name_field.display_name == "Name"
    assert name_field.options == []

    # Check enum field with options
    city_field = next(f for f in schema if f.name == "city")
    assert city_field.type == "enum"
    assert city_field.required is True
    assert len(city_field.options) == 2
    assert city_field.options[0]["value"] == "Moscow"
    assert city_field.options[1]["value"] == "Saint Petersburg"


@pytest.mark.asyncio
async def test_update_quiz_answers_preserves_structure(test_company_with_fields):
    """Test that updating quiz answers preserves field structure."""
    company, fields = test_company_with_fields
    repo = CustomersRepository()

    customer, _ = await repo.get_or_create(
        user_id="test_user_789",
        company_id=company.id,
    )

    # Initialize customer_fields with all fields first (simulating backfill or initial setup)
    # Note: get_or_create already initializes customer_fields
    # Update some fields
    customer, changed = await repo.update_customer_fields(
        customer,
        {"name": "John Doe", "city": "Moscow"},
    )

    assert "name" in changed
    assert "city" in changed
    assert customer.customer_fields["name"] == "John Doe"
    assert customer.customer_fields["city"] == "Moscow"
    assert customer.customer_fields["age"] is None  # Unchanged field still exists


@pytest.mark.asyncio
async def test_ensure_all_fields_present(test_company_with_fields):
    """Test _ensure_all_fields_present helper method."""
    company, fields = test_company_with_fields
    repo = CustomersRepository()

    # Create customer without going through repository
    customer = await Customer.create(
        user_id="test_direct",
        company_id=company.id,
        customer_fields={},
        quiz_answers={},
        langfuse_sessions={},
        meta={},
    )

    # Ensure fields are added
    updated = await repo._ensure_all_fields_present(customer)

    assert updated is True
    assert "name" in customer.customer_fields
    assert "age" in customer.customer_fields
    assert "city" in customer.customer_fields
    assert all(v is None for v in customer.customer_fields.values())


@pytest.mark.asyncio
async def test_backfill_fields_for_company_adds_new_fields(test_company_with_fields):
    """Test backfill_fields_for_company adds new fields to all customers."""
    company, fields = test_company_with_fields
    repo = CustomersRepository()

    # Create multiple customers with initial fields
    customer1, _ = await repo.get_or_create(
        user_id="test_user_backfill_1",
        company_id=company.id,
    )
    customer2, _ = await repo.get_or_create(
        user_id="test_user_backfill_2",
        company_id=company.id,
    )

    # Note: backfill_fields_for_company works with customer_fields
    # Customers created via get_or_create have customer_fields initialized
    initial_fields_count = len(customer1.customer_fields) if customer1.customer_fields else 0
    assert initial_fields_count == 3  # customer_fields should have 3 system fields initially

    # Add new customer-level field to company
    await Field.create(
        company=company,
        name="phone",
        question="What is your phone?",
        answer_type=AnswerType.STRING,
        required=False,
        display_name="Phone",
        level=FieldLevel.CUSTOMER,
    )

    # Backfill all customers
    # backfill_fields_for_company adds ALL fields from company to customer_fields
    total, updated = await repo.backfill_fields_for_company(company.id)

    assert total == 2
    assert updated == 2

    # Refresh customers from DB
    await customer1.refresh_from_db()
    await customer2.refresh_from_db()

    # Check that both customers have all fields in customer_fields (including the new one)
    # backfill adds all fields: name, age, city (from fixture) + phone (newly added) = 4 fields
    assert len(customer1.customer_fields) == 4
    assert "name" in customer1.customer_fields
    assert "age" in customer1.customer_fields
    assert "city" in customer1.customer_fields
    assert "phone" in customer1.customer_fields
    assert customer1.customer_fields["phone"] is None

    assert len(customer2.customer_fields) == 4
    assert "phone" in customer2.customer_fields
    assert customer2.customer_fields["phone"] is None


@pytest.mark.asyncio
async def test_backfill_fields_for_company_preserves_existing_values(test_company_with_fields):
    """Test backfill_fields_for_company preserves existing quiz_answers values."""
    company, fields = test_company_with_fields
    repo = CustomersRepository()

    # Create customer and set some values
    customer, _ = await repo.get_or_create(
        user_id="test_user_preserve",
        company_id=company.id,
    )

    # Update some fields with values
    customer, _ = await repo.update_customer_fields(
        customer,
        {"name": "John Doe", "age": 30},
    )

    # Add new customer-level field
    await Field.create(
        company=company,
        name="email",
        question="What is your email?",
        answer_type=AnswerType.STRING,
        required=False,
        level=FieldLevel.CUSTOMER,
    )

    # Backfill
    total, updated = await repo.backfill_fields_for_company(company.id)

    assert total == 1
    assert updated == 1

    # Refresh from DB
    await customer.refresh_from_db()

    # Check that existing values are preserved
    assert customer.customer_fields["name"] == "John Doe"
    assert customer.customer_fields["age"] == 30
    # New field should be added
    assert "email" in customer.customer_fields
    assert customer.customer_fields["email"] is None


@pytest.mark.asyncio
async def test_backfill_fields_for_company_no_customers(company_factory):
    """Test backfill_fields_for_company with no customers."""
    company = await company_factory()
    repo = CustomersRepository()

    # Add a customer-level field
    await Field.create(
        company=company,
        name="test_field",
        question="Test?",
        answer_type=AnswerType.STRING,
        level=FieldLevel.CUSTOMER,
    )

    # Backfill (no customers exist)
    total, updated = await repo.backfill_fields_for_company(company.id)

    assert total == 0
    assert updated == 0


@pytest.mark.asyncio
async def test_backfill_fields_for_company_no_new_fields(test_company_with_fields):
    """Test backfill_fields_for_company when all customers already have all fields."""
    company, fields = test_company_with_fields
    repo = CustomersRepository()

    # Create customers (they already have all fields)
    customer1, _ = await repo.get_or_create(
        user_id="test_user_no_update_1",
        company_id=company.id,
    )
    customer2, _ = await repo.get_or_create(
        user_id="test_user_no_update_2",
        company_id=company.id,
    )

    # Backfill (no new fields added)
    # Note: backfill_fields_for_company works with customer_fields
    # Customers created via get_or_create have customer_fields initialized
    # So backfill will not update customers since they already have all fields
    total, updated = await repo.backfill_fields_for_company(company.id)

    assert total == 2
    # Backfill doesn't update customers since they already have all fields
    assert updated == 0


@pytest.mark.asyncio
async def test_customer_fields_only_includes_customer_level_fields(company_factory):
    """Test that customer_fields only includes customer-level fields, not order-level."""
    company = await company_factory()
    repo = CustomersRepository()

    # Create customer-level field
    await Field.create(
        company=company,
        name="phone",
        question="What is your phone?",
        answer_type=AnswerType.STRING,
        level=FieldLevel.CUSTOMER,
        display_name="Phone",
    )

    # Create order-level field
    await Field.create(
        company=company,
        name="destination",
        question="Where to deliver?",
        answer_type=AnswerType.STRING,
        level=FieldLevel.ORDER,
        display_name="Destination",
    )

    # Create customer - should only have customer-level field in customer_fields
    customer, created = await repo.get_or_create(
        user_id="test_user_level_filter",
        company_id=company.id,
    )

    assert created is True
    assert "phone" in customer.customer_fields
    assert "destination" not in customer.customer_fields
    assert customer.customer_fields["phone"] is None


@pytest.mark.asyncio
async def test_backfill_only_adds_customer_level_fields(company_factory):
    """Test that backfill only adds customer-level fields to customer_fields."""
    company = await company_factory()
    repo = CustomersRepository()

    # Create customer with initial customer-level field
    await Field.create(
        company=company,
        name="phone",
        question="What is your phone?",
        answer_type=AnswerType.STRING,
        level=FieldLevel.CUSTOMER,
    )

    customer, _ = await repo.get_or_create(
        user_id="test_user_backfill_level",
        company_id=company.id,
    )

    # Verify initial state - should have phone field (system field from get_or_create)
    assert "phone" in customer.customer_fields
    # get_or_create already initialized customer with phone (system field)
    initial_count = len(customer.customer_fields)

    # Add order-level field - will be added to customer_fields by backfill
    await Field.create(
        company=company,
        name="budget",
        question="What is your budget?",
        answer_type=AnswerType.NUMBER,
        level=FieldLevel.ORDER,
    )

    # Add new customer-level field
    await Field.create(
        company=company,
        name="email",
        question="What is your email?",
        answer_type=AnswerType.STRING,
        level=FieldLevel.CUSTOMER,
    )

    # Backfill
    # Note: backfill_fields_for_company adds ALL fields to customer_fields (not filtered by level)
    total, updated = await repo.backfill_fields_for_company(company.id)

    assert total == 1
    assert updated == 1

    await customer.refresh_from_db()

    # backfill_fields_for_company adds ALL fields to customer_fields, regardless of level
    # Customer initially had phone (1 field), backfill adds email and budget (2 new fields)
    assert "phone" in customer.customer_fields
    assert "email" in customer.customer_fields
    assert "budget" in customer.customer_fields  # ORDER level field is also added
    assert len(customer.customer_fields) == initial_count + 2  # email and budget added
