"""Repository-layer tests for billing."""

from __future__ import annotations

import pytest

from src.backend.modules.billing.models import CompanyBalance, InitiatedBy, OperationType
from src.backend.modules.billing.repository import BillingRepository, LedgerRepository


@pytest.mark.asyncio
async def test_get_or_create_balance_existing(
    billing_repo: BillingRepository,
    company_with_balance: tuple,
):
    """Test get_or_create_balance returns existing balance."""
    company, balance = company_with_balance

    result = await billing_repo.get_or_create_balance(company.id)

    assert result.id == balance.id
    assert result.balance == balance.balance


@pytest.mark.asyncio
async def test_get_or_create_balance_creates_new(
    billing_repo: BillingRepository,
    company_factory,
):
    """Test get_or_create_balance creates new balance if missing."""
    company = await company_factory()

    balance_exists = await CompanyBalance.filter(company_id=company.id).exists()
    assert balance_exists is False

    result = await billing_repo.get_or_create_balance(company.id)

    assert result.company_id == company.id
    assert result.balance == 0


@pytest.mark.asyncio
async def test_get_balance_with_lock_existing(
    billing_repo: BillingRepository,
    company_with_balance: tuple,
):
    """Test get_balance_with_lock returns existing balance."""
    company, balance = company_with_balance

    from tortoise.transactions import in_transaction

    async with in_transaction() as connection:
        result = await billing_repo.get_balance_with_lock(company.id, connection)

        assert result is not None
        assert result.id == balance.id
        assert result.balance == balance.balance


@pytest.mark.asyncio
async def test_get_balance_with_lock_missing(
    billing_repo: BillingRepository,
    company_factory,
):
    """Test get_balance_with_lock returns None if balance doesn't exist."""
    company = await company_factory()

    from tortoise.transactions import in_transaction

    async with in_transaction() as connection:
        result = await billing_repo.get_balance_with_lock(company.id, connection)

        assert result is None


@pytest.mark.asyncio
async def test_increment_balance_existing(
    billing_repo: BillingRepository,
    company_with_balance: tuple,
):
    """Test increment_balance increments existing balance."""
    company, balance = company_with_balance
    initial_balance = balance.balance
    amount = 30

    from tortoise.transactions import in_transaction

    async with in_transaction() as connection:
        result_balance, new_balance = await billing_repo.increment_balance(company.id, amount, connection)

        assert result_balance.id == balance.id
        assert new_balance == initial_balance + amount
        assert result_balance.balance == new_balance


@pytest.mark.asyncio
async def test_increment_balance_creates_new(
    billing_repo: BillingRepository,
    company_factory,
):
    """Test increment_balance creates balance if missing."""
    company = await company_factory()
    amount = 50

    from tortoise.transactions import in_transaction

    async with in_transaction() as connection:
        result_balance, new_balance = await billing_repo.increment_balance(company.id, amount, connection)

        assert result_balance.company_id == company.id
        assert new_balance == amount
        assert result_balance.balance == amount


@pytest.mark.asyncio
async def test_decrement_balance_if_sufficient_success(
    billing_repo: BillingRepository,
    company_with_balance: tuple,
):
    """Test decrement_balance_if_sufficient succeeds when balance is sufficient."""
    company, balance = company_with_balance
    initial_balance = balance.balance
    amount = 3

    from tortoise.transactions import in_transaction

    async with in_transaction() as connection:
        result_balance, new_balance = await billing_repo.decrement_balance_if_sufficient(company.id, amount, connection)

        assert result_balance is not None
        assert new_balance == initial_balance - amount
        assert result_balance.balance == new_balance


@pytest.mark.asyncio
async def test_decrement_balance_if_sufficient_insufficient(
    billing_repo: BillingRepository,
    company_with_balance: tuple,
):
    """Test decrement_balance_if_sufficient fails when balance is insufficient."""
    company, balance = company_with_balance
    initial_balance = balance.balance
    amount = initial_balance + 10

    from tortoise.transactions import in_transaction

    async with in_transaction() as connection:
        result_balance, old_balance = await billing_repo.decrement_balance_if_sufficient(company.id, amount, connection)

        assert result_balance is None
        assert old_balance == initial_balance


@pytest.mark.asyncio
async def test_decrement_balance_if_sufficient_missing(
    billing_repo: BillingRepository,
    company_factory,
):
    """Test decrement_balance_if_sufficient returns None when balance doesn't exist."""
    company = await company_factory()
    amount = 10

    from tortoise.transactions import in_transaction

    async with in_transaction() as connection:
        result_balance, old_balance = await billing_repo.decrement_balance_if_sufficient(company.id, amount, connection)

        assert result_balance is None
        assert old_balance == 0


@pytest.mark.asyncio
async def test_create_ledger_entry(
    ledger_repo: LedgerRepository,
    company_factory,
):
    """Test create ledger entry."""
    company = await company_factory()

    entry = await ledger_repo.create_entry(
        company_id=company.id,
        operation_type=OperationType.TOP_UP,
        amount=100,
        initiated_by=InitiatedBy.OPERATOR,
        comment="Test entry",
    )

    assert entry.id is not None
    assert entry.company_id == company.id
    assert entry.operation_type == OperationType.TOP_UP
    assert entry.amount == 100
    assert entry.initiated_by == InitiatedBy.OPERATOR
    assert entry.comment == "Test entry"


@pytest.mark.asyncio
async def test_create_ledger_entry_with_order(
    ledger_repo: LedgerRepository,
    order_with_customer: tuple,
):
    """Test create ledger entry with order reference."""
    order, _, company = order_with_customer

    entry = await ledger_repo.create_entry(
        company_id=company.id,
        operation_type=OperationType.CHARGE,
        amount=-1,
        initiated_by=InitiatedBy.SYSTEM,
        order_id=order.id,
        channel_type="telegram",
        conversation_id="conv-123",
    )

    assert entry.id is not None
    assert entry.order_id == order.id
    assert entry.channel_type == "telegram"
    assert entry.conversation_id == "conv-123"


@pytest.mark.asyncio
async def test_find_charge_by_order_id_found(
    ledger_repo: LedgerRepository,
    order_with_customer: tuple,
):
    """Test find_charge_by_order_id finds existing charge."""
    order, _, company = order_with_customer

    entry = await ledger_repo.create_entry(
        company_id=company.id,
        operation_type=OperationType.CHARGE,
        amount=-1,
        initiated_by=InitiatedBy.SYSTEM,
        order_id=order.id,
    )

    found = await ledger_repo.find_charge_by_order_id(order.id)

    assert found is not None
    assert found.id == entry.id
    assert found.order_id == order.id


@pytest.mark.asyncio
async def test_find_charge_by_order_id_not_found(
    ledger_repo: LedgerRepository,
    order_with_customer: tuple,
):
    """Test find_charge_by_order_id returns None when not found."""
    order, _, _ = order_with_customer

    found = await ledger_repo.find_charge_by_order_id(order.id)

    assert found is None


@pytest.mark.asyncio
async def test_list_by_company_all(
    ledger_repo: LedgerRepository,
    company_factory,
):
    """Test list_by_company returns all entries."""
    company = await company_factory()

    await ledger_repo.create_entry(
        company_id=company.id,
        operation_type=OperationType.TOP_UP,
        amount=100,
        initiated_by=InitiatedBy.OPERATOR,
    )
    await ledger_repo.create_entry(
        company_id=company.id,
        operation_type=OperationType.CHARGE,
        amount=-1,
        initiated_by=InitiatedBy.SYSTEM,
    )

    entries, total = await ledger_repo.list_by_company(company_id=company.id)

    assert total == 2
    assert len(entries) == 2


@pytest.mark.asyncio
async def test_list_by_company_filter_operation_type(
    ledger_repo: LedgerRepository,
    company_factory,
):
    """Test list_by_company filters by operation_type."""
    company = await company_factory()

    await ledger_repo.create_entry(
        company_id=company.id,
        operation_type=OperationType.TOP_UP,
        amount=100,
        initiated_by=InitiatedBy.OPERATOR,
    )
    await ledger_repo.create_entry(
        company_id=company.id,
        operation_type=OperationType.CHARGE,
        amount=-1,
        initiated_by=InitiatedBy.SYSTEM,
    )

    entries, total = await ledger_repo.list_by_company(company_id=company.id, operation_type=OperationType.TOP_UP)

    assert total == 1
    assert len(entries) == 1
    assert entries[0].operation_type == OperationType.TOP_UP


@pytest.mark.asyncio
async def test_list_by_company_pagination(
    ledger_repo: LedgerRepository,
    company_factory,
):
    """Test list_by_company pagination."""
    company = await company_factory()

    for _i in range(10):
        await ledger_repo.create_entry(
            company_id=company.id,
            operation_type=OperationType.TOP_UP,
            amount=10,
            initiated_by=InitiatedBy.OPERATOR,
        )

    entries_page1, total = await ledger_repo.list_by_company(company_id=company.id, limit=5, offset=0)

    assert total == 10
    assert len(entries_page1) == 5

    entries_page2, total2 = await ledger_repo.list_by_company(company_id=company.id, limit=5, offset=5)

    assert total2 == 10
    assert len(entries_page2) == 5
    assert entries_page1[0].id != entries_page2[0].id


@pytest.mark.asyncio
async def test_list_by_company_filter_order_id(
    ledger_repo: LedgerRepository,
    order_with_customer: tuple,
):
    """Test list_by_company filters by order_id."""
    order, _, company = order_with_customer

    await ledger_repo.create_entry(
        company_id=company.id,
        operation_type=OperationType.CHARGE,
        amount=-1,
        initiated_by=InitiatedBy.SYSTEM,
        order_id=order.id,
    )
    await ledger_repo.create_entry(
        company_id=company.id,
        operation_type=OperationType.CHARGE,
        amount=-1,
        initiated_by=InitiatedBy.SYSTEM,
        order_id=None,
    )

    entries, total = await ledger_repo.list_by_company(company_id=company.id, order_id=order.id)

    assert total == 1
    assert len(entries) == 1
    assert entries[0].order_id == order.id
