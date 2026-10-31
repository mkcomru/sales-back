from __future__ import annotations

from datetime import datetime

from src.backend.modules.orders.models import Order
from src.backend.modules.users.models import CompanyUser


async def on_order_assigned_outside_working_hours(
    order: Order,
    manager: CompanyUser,
    next_working_time: datetime | None,
) -> None:
    """Notification hook for order assigned outside manager working hours.

    Args:
        order: Assigned order
        manager: Manager who was assigned
        next_working_time: Next working time for manager (in manager's timezone)

    MVP: no-op (pass)
    Future: schedule notification for next_working_time
    """
    pass
