"""Repository for billing operations."""

from datetime import datetime

from src.backend.modules.billing.models import BalanceLedger, CompanyBalance, InitiatedBy, OperationType
from src.backend.modules.core.base_repo import BaseRepository


class BillingRepository(BaseRepository[CompanyBalance]):
    def __init__(self):
        super().__init__(CompanyBalance)

    async def get_or_create_balance(self, company_id: int) -> CompanyBalance:
        """Get or create balance for company."""
        balance, _ = await CompanyBalance.get_or_create(
            company_id=company_id,
            defaults={"balance": 0},
        )
        return balance

    async def get_balance_with_lock(self, company_id: int, connection) -> CompanyBalance | None:
        """Get balance with row-level lock for transaction."""
        return await CompanyBalance.filter(company_id=company_id).select_for_update().using_db(connection).first()

    async def increment_balance(self, company_id: int, amount: int, connection) -> tuple[CompanyBalance, int]:
        """Increment balance atomically. Returns (balance, new_balance)."""
        balance = await self.get_balance_with_lock(company_id, connection)
        if not balance:
            balance = await CompanyBalance.create(company_id=company_id, balance=amount, using_db=connection)
            return balance, amount

        balance.balance += amount
        await balance.save(using_db=connection, update_fields=["balance", "updated_at"])
        return balance, balance.balance

    async def decrement_balance_if_sufficient(
        self, company_id: int, amount: int, connection
    ) -> tuple[CompanyBalance | None, int]:
        """Decrement balance if sufficient. Returns (balance, new_balance) or (None, old_balance) if insufficient."""
        balance = await self.get_balance_with_lock(company_id, connection)
        if not balance:
            return None, 0

        if balance.balance < amount:
            return None, balance.balance

        balance.balance -= amount
        await balance.save(using_db=connection, update_fields=["balance", "updated_at"])
        return balance, balance.balance


class LedgerRepository(BaseRepository[BalanceLedger]):
    def __init__(self):
        super().__init__(BalanceLedger)

    async def create_entry(
        self,
        company_id: int,
        operation_type: OperationType,
        amount: int,
        initiated_by: InitiatedBy,
        operator_id: int | None = None,
        comment: str | None = None,
        order_id: int | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        connection=None,
    ) -> BalanceLedger:
        """Create ledger entry."""
        kwargs = {
            "company_id": company_id,
            "operation_type": operation_type,
            "amount": amount,
            "initiated_by": initiated_by,
            "operator_id": operator_id,
            "comment": comment,
            "order_id": order_id,
            "channel_type": channel_type,
            "conversation_id": conversation_id,
        }
        if connection:
            return await BalanceLedger.create(using_db=connection, **kwargs)
        return await BalanceLedger.create(**kwargs)

    async def find_charge_by_order_id(self, order_id: int, connection=None) -> BalanceLedger | None:
        """Find existing charge entry for order (idempotency check)."""
        query = BalanceLedger.filter(order_id=order_id, operation_type=OperationType.CHARGE)
        if connection:
            return await query.using_db(connection).first()
        return await query.first()

    async def list_by_company(
        self,
        company_id: int,
        operation_type: OperationType | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        order_id: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[BalanceLedger], int]:
        """List ledger entries for company with filters."""
        query = BalanceLedger.filter(company_id=company_id)

        if operation_type:
            query = query.filter(operation_type=operation_type)
        if from_date:
            query = query.filter(timestamp__gte=from_date)
        if to_date:
            query = query.filter(timestamp__lte=to_date)
        if order_id:
            query = query.filter(order_id=order_id)

        total = await query.count()
        entries = await query.order_by("-timestamp").limit(limit).offset(offset).all()

        return entries, total
