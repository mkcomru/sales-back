"""Dependencies for orders module."""

from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from src.backend.modules.orders.service import OrderService


@lru_cache
def order_service() -> OrderService:
    return OrderService()


OrderServiceDep = Annotated[OrderService, Depends(order_service)]
