from typing import Annotated, Any

from fastapi import Depends, HTTPException, status

from src.backend.modules.auth.dependencies import CompanyManagerDep
from src.backend.modules.chat.models import Customer, Thread
from src.backend.modules.chat.service import ChatService
from src.backend.modules.chat.threads_service import ThreadsService
from src.backend.modules.chat.websocket import WebSocketManager, get_websocket_manager
from src.backend.modules.core.dependencies import SalesAgentClientDep
from src.backend.modules.orders.dependencies import OrderServiceDep
from src.backend.modules.users.models import UserRole
from src.backend.services.redis import RedisKVClient, get_redis_client


def threads_service(sales_agent_client: SalesAgentClientDep) -> ThreadsService:
    return ThreadsService(sales_agent_client=sales_agent_client)


ThreadsServiceDep = Annotated[ThreadsService, Depends(threads_service)]


def chat_service(
    order_service: OrderServiceDep,
    threads_svc: ThreadsServiceDep,
    sales_agent_client: SalesAgentClientDep,
) -> ChatService:
    return ChatService(
        order_service=order_service,
        threads_service=threads_svc,
        sales_agent_client=sales_agent_client,
    )


ChatServiceDep = Annotated[ChatService, Depends(chat_service)]


async def require_thread_manager_access(
    thread_id: str,
    company_user: CompanyManagerDep,
    chat_service: ChatServiceDep,
    order_service: OrderServiceDep,
) -> Any:
    """Require manager-level access to a thread.

    Rules:
    - ADMIN / OWNER => access to all threads in company
    - If order.assignee_id is None and role >= MANAGER => access
    - If order.assignee_id == company_user.id => access
    Otherwise: raise 403 (access denied).
    """
    thread = await chat_service.get_thread_by_id(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    if thread.company_id != company_user.company_id:
        # Thread exists but belongs to another company -> forbidden
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    # Admin/owner can access any thread
    if company_user.role in (UserRole.ADMIN, UserRole.OWNER):
        return thread

    # Check order assignee
    order = await order_service.ensure_active_order(thread)
    if order.assignee_id is None and company_user.role == UserRole.MANAGER:
        return thread

    # Assigned to this manager?
    if order.assignee_id == company_user.id:
        return thread

    # Otherwise deny
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")


async def require_customer_manager_access(
    customer_id: int,
    company_user: CompanyManagerDep,
    chat_service: ChatServiceDep,
) -> Any:
    """Require manager-level access to a customer.

    Rules:
    - ADMIN / OWNER => access to all customers in company
    - Otherwise manager must have at least
    one thread for this customer assigned to them.
    """
    try:
        customer = await chat_service.get_customer_detail(customer_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    if customer.company_id != company_user.company_id:
        # Customer exists but belongs to another company -> forbidden
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    # Admin/owner have access
    if company_user.role in (UserRole.ADMIN, UserRole.OWNER):
        return customer

    # Check if there's an order for this customer assigned to this manager
    # AICODE-NOTE: Check orders instead of threads since assignee moved to Order
    from src.backend.modules.orders.models import Order

    assigned_order = await Order.filter(
        customer_id=customer.id, assignee_id=company_user.id, closed_at__isnull=True
    ).first()
    if assigned_order:
        return customer

    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")


# Dependency types
ThreadManagerDep = Annotated[Thread, Depends(require_thread_manager_access)]
CustomerManagerDep = Annotated[Customer, Depends(require_customer_manager_access)]
RedisClientDep = Annotated[RedisKVClient, Depends(get_redis_client)]
WebSocketManagerDep = Annotated[WebSocketManager, Depends(get_websocket_manager)]
