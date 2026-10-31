"""Billing module dependencies."""

from typing import Annotated

from fastapi import Depends

from src.backend.modules.billing.repository import BillingRepository, LedgerRepository
from src.backend.modules.billing.service import BillingService


def get_billing_repository() -> BillingRepository:
    """Get billing repository instance."""
    return BillingRepository()


def get_ledger_repository() -> LedgerRepository:
    """Get ledger repository instance."""
    return LedgerRepository()


def get_billing_service(
    billing_repo: Annotated[BillingRepository, Depends(get_billing_repository)],
    ledger_repo: Annotated[LedgerRepository, Depends(get_ledger_repository)],
) -> BillingService:
    """Get billing service instance."""
    return BillingService(billing_repo, ledger_repo)


BillingServiceDep = Annotated[BillingService, Depends(get_billing_service)]
