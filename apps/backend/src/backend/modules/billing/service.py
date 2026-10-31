"""Billing service for balance management."""

from __future__ import annotations

import structlog
from tortoise.transactions import in_transaction

from src.backend.modules.billing.models import BillingStatus, CompanyBalance, InitiatedBy, OperationType
from src.backend.modules.billing.repository import BillingRepository, LedgerRepository
from src.backend.modules.billing.schemas import ChargeResult
from src.backend.modules.chat.models import Thread
from src.backend.modules.orders.models import Order

log = structlog.get_logger(__name__)


class BillingService:
    """Service for managing company lead balances."""

    CHARGE_AMOUNT = 1

    def __init__(self, billing_repo: BillingRepository, ledger_repo: LedgerRepository):
        self.billing_repo = billing_repo
        self.ledger_repo = ledger_repo

    async def top_up(
        self,
        company_id: int,
        amount: int,
        operator_id: int | None = None,
        comment: str | None = None,
        initiated_by: InitiatedBy = InitiatedBy.OPERATOR,
    ) -> tuple[int, int]:
        """Top up company balance.

        Args:
            company_id: Company ID
            amount: Amount to add (must be > 0)
            operator_id: Operator ID (for manual operations)
            comment: Optional comment
            initiated_by: Who initiated the operation

        Returns:
            Tuple of (balance_id, ledger_entry_id)
        """
        async with in_transaction() as connection:
            balance, new_balance = await self.billing_repo.increment_balance(company_id, amount, connection)

            ledger_entry = await self.ledger_repo.create_entry(
                company_id=company_id,
                operation_type=OperationType.TOP_UP,
                amount=amount,
                initiated_by=initiated_by,
                operator_id=operator_id,
                comment=comment,
                connection=connection,
            )

            log.info(
                "billing.top_up.success",
                company_id=company_id,
                amount=amount,
                new_balance=new_balance,
                ledger_entry_id=ledger_entry.id,
                operator_id=operator_id,
            )

            return balance.id, ledger_entry.id

    async def charge_for_order(
        self,
        company_id: int,
        order_id: int,
        channel_type: str,
        conversation_id: str | None = None,
    ) -> ChargeResult:
        """Charge company for order creation.

        Idempotent: if order already charged, returns success with existing entry.

        Args:
            company_id: Company ID
            order_id: Order database ID
            channel_type: Channel type (denormalized for querying)
            conversation_id: Conversation ID (denormalized for querying)

        Returns:
            ChargeResult with success status, balance, and billing_status
        """
        async with in_transaction() as connection:
            existing_charge = await self.ledger_repo.find_charge_by_order_id(order_id, connection)
            if existing_charge:
                log.info(
                    "billing.charge.idempotent",
                    order_id=order_id,
                    company_id=company_id,
                    ledger_entry_id=existing_charge.id,
                )
                balance_row = await self.billing_repo.get_balance_with_lock(company_id, connection)
                if not balance_row:
                    balance_row = await CompanyBalance.create(company_id=company_id, balance=0, using_db=connection)
                return ChargeResult(
                    success=True,
                    new_balance=balance_row.balance,
                    ledger_entry_id=existing_charge.id,
                    already_charged=True,
                    billing_status=BillingStatus.ACTIVE,
                )

            balance_row = await self.billing_repo.get_balance_with_lock(company_id, connection)
            if not balance_row:
                balance_row = await CompanyBalance.create(company_id=company_id, balance=0, using_db=connection)

            if balance_row.balance < self.CHARGE_AMOUNT:
                ledger_entry = await self.ledger_repo.create_entry(
                    company_id=company_id,
                    operation_type=OperationType.CHARGE,
                    amount=0,
                    initiated_by=InitiatedBy.SYSTEM,
                    order_id=order_id,
                    channel_type=channel_type,
                    conversation_id=conversation_id,
                    connection=connection,
                )

                order = await Order.filter(id=order_id).using_db(connection).first()
                if order:
                    order.billing_status = BillingStatus.BILLING_HOLD
                    await order.save(using_db=connection, update_fields=["billing_status"])

                log.warning(
                    "billing.charge.failed_zero_balance",
                    order_id=order_id,
                    company_id=company_id,
                    balance=balance_row.balance,
                    ledger_entry_id=ledger_entry.id,
                )

                return ChargeResult(
                    success=False,
                    new_balance=balance_row.balance,
                    ledger_entry_id=ledger_entry.id,
                    already_charged=False,
                    billing_status=BillingStatus.BILLING_HOLD,
                )

            balance_row.balance -= self.CHARGE_AMOUNT
            await balance_row.save(using_db=connection, update_fields=["balance", "updated_at"])

            ledger_entry = await self.ledger_repo.create_entry(
                company_id=company_id,
                operation_type=OperationType.CHARGE,
                amount=-self.CHARGE_AMOUNT,
                initiated_by=InitiatedBy.SYSTEM,
                order_id=order_id,
                channel_type=channel_type,
                conversation_id=conversation_id,
                connection=connection,
            )

            order = await Order.filter(id=order_id).using_db(connection).first()
            if order:
                order.billing_status = BillingStatus.ACTIVE
                order.charged_at = ledger_entry.timestamp
                await order.save(using_db=connection, update_fields=["billing_status", "charged_at"])

            log.info(
                "billing.charge.success",
                order_id=order_id,
                company_id=company_id,
                new_balance=balance_row.balance,
                ledger_entry_id=ledger_entry.id,
            )

            return ChargeResult(
                success=True,
                new_balance=balance_row.balance,
                ledger_entry_id=ledger_entry.id,
                already_charged=False,
                billing_status=BillingStatus.ACTIVE,
            )

    async def get_balance(self, company_id: int) -> tuple[int, bool]:
        """Get company balance.

        Args:
            company_id: Company ID

        Returns:
            Tuple of (balance, balance_warning) where warning is True if balance = 0
        """
        balance = await self.billing_repo.get_or_create_balance(company_id)
        return balance.balance, balance.balance == 0

    async def reactivate_thread(
        self,
        company_id: int,
        thread_id: int,
    ) -> ChargeResult:
        """Reactivate a thread that was on billing hold.

        Attempts to charge for the order if it wasn't already charged.
        If balance is sufficient, sets billing_status to ACTIVE.

        Args:
            company_id: Company ID
            thread_id: Thread database ID

        Returns:
            ChargeResult with success status and billing_status
        """
        thread = await Thread.filter(id=thread_id, company_id=company_id).prefetch_related("active_order").first()
        if not thread:
            raise ValueError(f"Thread {thread_id} not found for company {company_id}")

        if not thread.active_order:
            raise ValueError(f"Thread {thread_id} has no active order")

        order = thread.active_order

        if order.billing_status != BillingStatus.BILLING_HOLD:
            balance_row = await self.billing_repo.get_or_create_balance(company_id)
            return ChargeResult(
                success=True,
                new_balance=balance_row.balance,
                ledger_entry_id=None,
                already_charged=True,
                billing_status=order.billing_status,
            )

        return await self.charge_for_order(
            company_id=company_id,
            order_id=order.id,
            channel_type=thread.channel_type,
            conversation_id=thread.conversation_id,
        )

    async def reactivate_threads(
        self,
        company_id: int,
        thread_ids: list[int],
    ) -> dict[int, ChargeResult]:
        """Reactivate multiple threads that were on billing hold.

        Args:
            company_id: Company ID
            thread_ids: List of thread database IDs

        Returns:
            Dictionary mapping thread_id to ChargeResult
        """
        results: dict[int, ChargeResult] = {}
        for thread_id in thread_ids:
            try:
                result = await self.reactivate_thread(company_id, thread_id)
                results[thread_id] = result
            except Exception as exc:
                log.error(
                    "billing.reactivate_thread.error",
                    company_id=company_id,
                    thread_id=thread_id,
                    error=str(exc),
                    exc_info=True,
                )
                balance_row = await self.billing_repo.get_or_create_balance(company_id)
                results[thread_id] = ChargeResult(
                    success=False,
                    new_balance=balance_row.balance,
                    ledger_entry_id=None,
                    already_charged=False,
                    billing_status=BillingStatus.BILLING_HOLD,
                )
        return results
