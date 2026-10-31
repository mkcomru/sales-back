"""CRUD API endpoints for ping rules."""

from __future__ import annotations

from fastapi import APIRouter, status

from src.backend.modules.auth.dependencies import CompanyAdminDep
from src.backend.modules.pings.dependencies import PingServiceDep
from src.backend.modules.pings.schemas import (
    PingRuleCreateRequest,
    PingRuleReorderRequest,
    PingRuleResponse,
    PingRuleUpdateRequest,
)

router = APIRouter(prefix="/companies/{company_id}", tags=["pings"])


@router.get("/stages/{stage_id}/pings", response_model=list[PingRuleResponse])
async def list_ping_rules(
    company_id: int,
    stage_id: int,
    service: PingServiceDep,
    user: CompanyAdminDep,
) -> list[PingRuleResponse]:
    rules = await service.list_rules(stage_id)
    return [PingRuleResponse.from_model(r) for r in rules]


@router.post(
    "/stages/{stage_id}/pings",
    response_model=PingRuleResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_ping_rule(
    company_id: int,
    stage_id: int,
    data: PingRuleCreateRequest,
    service: PingServiceDep,
    user: CompanyAdminDep,
) -> PingRuleResponse:
    rule = await service.create_rule(company_id, stage_id, data)
    return PingRuleResponse.from_model(rule)


@router.patch("/pings/{ping_id}", response_model=PingRuleResponse)
async def update_ping_rule(
    company_id: int,
    ping_id: int,
    data: PingRuleUpdateRequest,
    service: PingServiceDep,
    user: CompanyAdminDep,
) -> PingRuleResponse:
    rule = await service.update_rule(company_id, ping_id, data)
    return PingRuleResponse.from_model(rule)


@router.delete("/pings/{ping_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_ping_rule(
    company_id: int,
    ping_id: int,
    service: PingServiceDep,
    user: CompanyAdminDep,
) -> None:
    await service.delete_rule(company_id, ping_id)


@router.post("/stages/{stage_id}/pings/reorder", response_model=list[PingRuleResponse])
async def reorder_ping_rules(
    company_id: int,
    stage_id: int,
    data: PingRuleReorderRequest,
    service: PingServiceDep,
    user: CompanyAdminDep,
) -> list[PingRuleResponse]:
    rules = await service.reorder_rules(company_id, stage_id, data.ping_rule_ids)
    return [PingRuleResponse.from_model(r) for r in rules]
