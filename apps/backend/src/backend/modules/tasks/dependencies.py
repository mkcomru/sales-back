"""Dependencies for tasks module."""

from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from src.backend.modules.orders.dependencies import order_service
from src.backend.modules.tasks.repository import TaskRepository
from src.backend.modules.tasks.service import TaskService


@lru_cache
def task_repository() -> TaskRepository:
    return TaskRepository()


@lru_cache
def task_service() -> TaskService:
    return TaskService(task_repository(), order_service())


TaskRepositoryDep = Annotated[TaskRepository, Depends(task_repository)]
TaskServiceDep = Annotated[TaskService, Depends(task_service)]
