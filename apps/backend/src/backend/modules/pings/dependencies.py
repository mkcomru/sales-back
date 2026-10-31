"""Dependencies for pings module."""

from typing import Annotated

from fastapi import Depends

from src.backend.modules.pings.repository import PingRuleRepository
from src.backend.modules.pings.service import PingService
from src.backend.modules.tasks.dependencies import TaskServiceDep


def ping_rule_repository() -> PingRuleRepository:
    return PingRuleRepository()


PingRuleRepositoryDep = Annotated[PingRuleRepository, Depends(ping_rule_repository)]


def ping_service(
    ping_repo: PingRuleRepositoryDep,
    task_service: TaskServiceDep,
) -> PingService:
    return PingService(ping_repo=ping_repo, task_service=task_service)


PingServiceDep = Annotated[PingService, Depends(ping_service)]
