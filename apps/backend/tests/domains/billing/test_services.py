"""Service-layer tests for billing."""

from __future__ import annotations

import pytest

from src.backend.modules.billing.models import BillingStatus, CompanyBalance, InitiatedBy, OperationType
from src.backend.modules.billing.repository import LedgerRepository
from src.backend.modules.billing.service import BillingService
from src.backend.modules.orders.models import Order


@pytest.mark.asyncio
async def test_charge_for_order_success(
    billing_service: BillingService,
    company_with_balance: tuple,
    order_with_customer: tuple,
):
    """Test successful charge for new order."""
    company, balance = company_with_balance
    order, _, _ = order_with_customer
    order.company_id = company.id
    await order.save()

    result = await billing_service.charge_for_order(
        company_id=company.id,
        order_id=order.id,
        channel_type="telegram",
        conversation_id="conv-123",
    )

    assert result.success is True
    assert result.new_balance == balance.balance - 1
    assert result.already_charged is False
    assert result.billing_status == BillingStatus.ACTIVE
    assert result.ledger_entry_id is not None

    updated_balance = await CompanyBalance.get(company_id=company.id)
    assert updated_balance.balance == balance.balance - 1

    updated_order = await Order.get(id=order.id)
    assert updated_order.billing_status == BillingStatus.ACTIVE
    assert updated_order.charged_at is not None


@pytest.mark.asyncio
async def test_charge_for_order_zero_balance(
    billing_service: BillingService,
    company_with_zero_balance: tuple,
    order_with_customer: tuple,
):
    """Test charge fails when balance is zero."""
    company, balance = company_with_zero_balance
    order, _, _ = order_with_customer
    order.company_id = company.id
    await order.save()

    result = await billing_service.charge_for_order(
        company_id=company.id,
        order_id=order.id,
        channel_type="telegram",
        conversation_id="conv-123",
    )

    assert result.success is False
    assert result.new_balance == 0
    assert result.already_charged is False
    assert result.billing_status == BillingStatus.BILLING_HOLD
    assert result.ledger_entry_id is not None

    updated_balance = await CompanyBalance.get(company_id=company.id)
    assert updated_balance.balance == 0

    updated_order = await Order.get(id=order.id)
    assert updated_order.billing_status == BillingStatus.BILLING_HOLD
    assert updated_order.charged_at is None


@pytest.mark.asyncio
async def test_charge_for_order_idempotent(
    billing_service: BillingService,
    company_with_balance: tuple,
    order_with_customer: tuple,
):
    """Test charge is idempotent - second call returns success without charging."""
    company, balance = company_with_balance
    order, _, _ = order_with_customer
    order.company_id = company.id
    await order.save()

    result1 = await billing_service.charge_for_order(
        company_id=company.id,
        order_id=order.id,
        channel_type="telegram",
        conversation_id="conv-123",
    )

    assert result1.success is True
    assert result1.already_charged is False
    initial_balance = result1.new_balance

    result2 = await billing_service.charge_for_order(
        company_id=company.id,
        order_id=order.id,
        channel_type="telegram",
        conversation_id="conv-123",
    )

    assert result2.success is True
    assert result2.already_charged is True
    assert result2.new_balance == initial_balance
    assert result2.ledger_entry_id == result1.ledger_entry_id

    updated_balance = await CompanyBalance.get(company_id=company.id)
    assert updated_balance.balance == initial_balance


@pytest.mark.asyncio
async def test_charge_for_order_creates_balance_if_missing(
    billing_service: BillingService,
    company_factory,
    order_with_customer: tuple,
):
    """Test charge creates balance record if it doesn't exist."""
    company = await company_factory()
    order, _, _ = order_with_customer
    order.company_id = company.id
    await order.save()

    balance_exists = await CompanyBalance.filter(company_id=company.id).exists()
    assert balance_exists is False

    result = await billing_service.charge_for_order(
        company_id=company.id,
        order_id=order.id,
        channel_type="telegram",
        conversation_id="conv-123",
    )

    assert result.success is False
    assert result.new_balance == 0
    assert result.billing_status == BillingStatus.BILLING_HOLD

    balance = await CompanyBalance.get(company_id=company.id)
    assert balance.balance == 0


@pytest.mark.asyncio
async def test_top_up_success(
    billing_service: BillingService,
    company_with_balance: tuple,
    operator_user: tuple,
):
    """Test successful top-up."""
    company, balance = company_with_balance
    company_user, _, _ = operator_user
    company_user.company_id = company.id
    await company_user.save()

    initial_balance = balance.balance
    amount = 50

    balance_id, ledger_entry_id = await billing_service.top_up(
        company_id=company.id,
        amount=amount,
        operator_id=company_user.id,
        comment="Test top-up",
        initiated_by=InitiatedBy.OPERATOR,
    )

    assert balance_id == balance.id
    assert ledger_entry_id is not None

    updated_balance = await CompanyBalance.get(company_id=company.id)
    assert updated_balance.balance == initial_balance + amount


@pytest.mark.asyncio
async def test_top_up_creates_balance_if_missing(
    billing_service: BillingService,
    company_factory,
    operator_user: tuple,
):
    """Test top-up creates balance record if it doesn't exist."""
    company = await company_factory()
    company_user, _, _ = operator_user
    company_user.company_id = company.id
    await company_user.save()

    balance_exists = await CompanyBalance.filter(company_id=company.id).exists()
    assert balance_exists is False

    amount = 100
    balance_id, ledger_entry_id = await billing_service.top_up(
        company_id=company.id,
        amount=amount,
        operator_id=company_user.id,
        comment="Initial top-up",
    )

    assert balance_id is not None
    assert ledger_entry_id is not None

    balance = await CompanyBalance.get(company_id=company.id)
    assert balance.balance == amount


@pytest.mark.asyncio
async def test_get_balance_existing(
    billing_service: BillingService,
    company_with_balance: tuple,
):
    """Test get balance for existing company."""
    company, balance = company_with_balance

    result_balance, balance_warning = await billing_service.get_balance(company.id)

    assert result_balance == balance.balance
    assert balance_warning is False


@pytest.mark.asyncio
async def test_get_balance_zero_warning(
    billing_service: BillingService,
    company_with_zero_balance: tuple,
):
    """Test get balance returns warning when balance is zero."""
    company, _ = company_with_zero_balance

    result_balance, balance_warning = await billing_service.get_balance(company.id)

    assert result_balance == 0
    assert balance_warning is True


@pytest.mark.asyncio
async def test_get_balance_creates_if_missing(
    billing_service: BillingService,
    company_factory,
):
    """Test get balance creates balance record if it doesn't exist."""
    company = await company_factory()

    balance_exists = await CompanyBalance.filter(company_id=company.id).exists()
    assert balance_exists is False

    result_balance, balance_warning = await billing_service.get_balance(company.id)

    assert result_balance == 0
    assert balance_warning is True

    balance = await CompanyBalance.get(company_id=company.id)
    assert balance.balance == 0


@pytest.mark.asyncio
async def test_charge_amount_constant(
    billing_service: BillingService,
    company_with_balance: tuple,
    order_with_customer: tuple,
):
    """Test charge amount is always 1 (constant pricing)."""
    company, balance = company_with_balance
    order, _, _ = order_with_customer
    order.company_id = company.id
    await order.save()

    initial_balance = balance.balance

    result = await billing_service.charge_for_order(
        company_id=company.id,
        order_id=order.id,
        channel_type="telegram",
        conversation_id="conv-123",
    )

    assert result.success is True
    assert result.new_balance == initial_balance - BillingService.CHARGE_AMOUNT
    assert BillingService.CHARGE_AMOUNT == 1


@pytest.mark.asyncio
async def test_charge_ledger_entry_created(
    billing_service: BillingService,
    ledger_repo: LedgerRepository,
    company_with_balance: tuple,
    order_with_customer: tuple,
):
    """Test charge creates proper ledger entry."""
    company, balance = company_with_balance
    order, _, _ = order_with_customer
    order.company_id = company.id
    await order.save()

    result = await billing_service.charge_for_order(
        company_id=company.id,
        order_id=order.id,
        channel_type="telegram",
        conversation_id="conv-123",
    )

    assert result.ledger_entry_id is not None

    ledger_entry = await ledger_repo.find_charge_by_order_id(order.id)
    assert ledger_entry is not None
    assert ledger_entry.company_id == company.id
    assert ledger_entry.operation_type == OperationType.CHARGE
    assert ledger_entry.amount == -1
    assert ledger_entry.order_id == order.id
    assert ledger_entry.channel_type == "telegram"
    assert ledger_entry.conversation_id == "conv-123"
    assert ledger_entry.initiated_by == InitiatedBy.SYSTEM


@pytest.mark.asyncio
async def test_top_up_ledger_entry_created(
    billing_service: BillingService,
    ledger_repo: LedgerRepository,
    company_with_balance: tuple,
    operator_user: tuple,
):
    """Test top-up creates proper ledger entry."""
    company, balance = company_with_balance
    company_user, _, _ = operator_user
    company_user.company_id = company.id
    await company_user.save()

    amount = 25
    comment = "Test top-up comment"

    balance_id, ledger_entry_id = await billing_service.top_up(
        company_id=company.id,
        amount=amount,
        operator_id=company_user.id,
        comment=comment,
        initiated_by=InitiatedBy.OPERATOR,
    )

    assert ledger_entry_id is not None

    entries, _ = await ledger_repo.list_by_company(company_id=company.id, limit=1)
    assert len(entries) == 1

    ledger_entry = entries[0]
    assert ledger_entry.company_id == company.id
    assert ledger_entry.operation_type == OperationType.TOP_UP
    assert ledger_entry.amount == amount
    assert ledger_entry.operator_id == company_user.id
    assert ledger_entry.comment == comment
    assert ledger_entry.initiated_by == InitiatedBy.OPERATOR
