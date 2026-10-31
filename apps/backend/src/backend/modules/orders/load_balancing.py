from __future__ import annotations

from datetime import UTC, datetime

from src.backend.modules.companies.models import Company
from src.backend.modules.orders.models import Order
from src.backend.modules.users.models import CompanyUser
from src.backend.modules.users.schedule_service import schedule_service


async def load_score(manager: CompanyUser) -> int:
    active_orders_count = await Order.filter(
        assignee_id=manager.id,
        closed_at__isnull=True,
    ).count()
    return active_orders_count


async def select_manager(company: Company) -> CompanyUser | None:
    available_managers = await schedule_service.get_available_managers(company)

    if not available_managers:
        return None

    working_managers = [manager for manager in available_managers if schedule_service.is_manager_working_now(manager)]

    candidates = working_managers if working_managers else available_managers

    if not candidates:
        return None

    managers_with_scores = []
    for manager in candidates:
        score = await load_score(manager)
        managers_with_scores.append((manager, score))

    managers_with_scores.sort(
        key=lambda x: (
            x[1],
            x[0].last_assigned_at if x[0].last_assigned_at is not None else datetime.min.replace(tzinfo=UTC),
        )
    )

    if managers_with_scores:
        return managers_with_scores[0][0]

    return None
