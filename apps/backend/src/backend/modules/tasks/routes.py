"""Task API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from common.models.pagination import PaginationParams

from src.backend.modules.auth.dependencies import require_company_manager, require_company_viewer
from src.backend.modules.core.dependencies import require_service_api_key
from src.backend.modules.tasks.dependencies import TaskServiceDep
from src.backend.modules.tasks.schemas import CreateOrderTaskRequest, TaskListResponse, TaskResponse, UpdateTaskRequest
from src.backend.modules.users.models import CompanyUser

router = APIRouter(prefix="/companies/{company_id}", tags=["tasks"])
internal_router = APIRouter(prefix="/internal/tasks", tags=["tasks:internal"])


@router.get("/orders/{order_id}/tasks", response_model=TaskListResponse)
async def list_order_tasks(
    company_id: int,
    order_id: int,
    service: TaskServiceDep,
    user: CompanyUser = Depends(require_company_viewer),
    include_completed: bool = Query(default=False, description="Include completed tasks"),
    pagination: PaginationParams = Depends(),
) -> TaskListResponse:
    """List tasks for an order."""
    tasks = await service.repo.get_tasks_for_order(
        company_id=company_id,
        order_id=order_id,
        include_completed=include_completed,
    )

    total = len(tasks)
    items = tasks[pagination.offset : pagination.offset + pagination.limit]
    task_responses = [TaskResponse.from_model(task) for task in items]

    return TaskListResponse(
        items=task_responses,
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.get("/orders/{order_id}/tasks/{task_id}", response_model=TaskResponse)
async def get_order_task(
    company_id: int,
    order_id: int,
    task_id: int,
    service: TaskServiceDep,
    user: CompanyUser = Depends(require_company_viewer),
) -> TaskResponse:
    """Get a single task for an order."""
    task = await service.get_order_task(company_id, order_id, task_id)
    return TaskResponse.from_model(task)


@router.post("/orders/{order_id}/tasks", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_order_task(
    company_id: int,
    order_id: int,
    data: CreateOrderTaskRequest,
    service: TaskServiceDep,
    user: CompanyUser = Depends(require_company_manager),
) -> TaskResponse:
    """Create a task for an order."""
    try:
        task = await service.create_order_task(
            company_id=company_id,
            order_id=order_id,
            data=data,
            created_by_id=user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return TaskResponse.from_model(task)


@router.patch("/orders/{order_id}/tasks/{task_id}", response_model=TaskResponse)
async def update_task(
    company_id: int,
    order_id: int,
    task_id: int,
    data: UpdateTaskRequest,
    service: TaskServiceDep,
    user: CompanyUser = Depends(require_company_manager),
) -> TaskResponse:
    """Update task fields (title, description, due_date, assignee)."""
    updates = data.model_dump(exclude_unset=True)
    task = await service.repo.update_task(task_id, **updates)
    return TaskResponse.from_model(task)


@router.post("/orders/{order_id}/tasks/{task_id}/complete", response_model=TaskResponse)
async def complete_task(
    company_id: int,
    order_id: int,
    task_id: int,
    service: TaskServiceDep,
    user: CompanyUser = Depends(require_company_manager),
) -> TaskResponse:
    """Mark a task as completed."""
    task = await service.complete_task(company_id=company_id, task_id=task_id)
    return TaskResponse.from_model(task)


@router.post("/orders/{order_id}/tasks/{task_id}/cancel", response_model=TaskResponse)
async def cancel_task(
    company_id: int,
    order_id: int,
    task_id: int,
    service: TaskServiceDep,
    user: CompanyUser = Depends(require_company_manager),
) -> TaskResponse:
    """Cancel a task."""
    task = await service.repo.cancel_task(task_id)
    return TaskResponse.from_model(task)


@router.get("/my-tasks", response_model=TaskListResponse)
async def list_my_tasks(
    company_id: int,
    service: TaskServiceDep,
    user: CompanyUser = Depends(require_company_viewer),
    include_completed: bool = Query(default=False, description="Include completed tasks"),
    pagination: PaginationParams = Depends(),
) -> TaskListResponse:
    """List tasks assigned to the current user."""
    tasks = await service.repo.get_tasks_for_assignee(
        company_id=company_id,
        assignee_id=user.id,
        include_completed=include_completed,
    )

    total = len(tasks)
    items = tasks[pagination.offset : pagination.offset + pagination.limit]
    task_responses = [TaskResponse.from_model(task) for task in items]

    return TaskListResponse(
        items=task_responses,
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.get("/tasks", response_model=TaskListResponse)
async def list_all_company_tasks(
    company_id: int,
    service: TaskServiceDep,
    user: CompanyUser = Depends(require_company_viewer),
    include_completed: bool = Query(default=False, description="Include completed tasks"),
    pagination: PaginationParams = Depends(),
) -> TaskListResponse:
    """List company tasks visible to the current member (same access as order-scoped task views)."""
    tasks = await service.repo.get_all_company_tasks(
        company_id=company_id,
        include_completed=include_completed,
    )

    total = len(tasks)
    items = tasks[pagination.offset : pagination.offset + pagination.limit]
    task_responses = [TaskResponse.from_model(task) for task in items]

    return TaskListResponse(
        items=task_responses,
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
    )


@internal_router.post(
    "/companies/{company_id}/orders/{order_id}",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_service_api_key)],
)
async def create_order_task_internal(
    company_id: int,
    order_id: int,
    data: CreateOrderTaskRequest,
    service: TaskServiceDep,
) -> TaskResponse:
    """Create a task for an order (internal API for Sales-Agent)."""
    try:
        task = await service.create_order_task(
            company_id=company_id,
            order_id=order_id,
            data=data,
            created_by_id=None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return TaskResponse.from_model(task)
