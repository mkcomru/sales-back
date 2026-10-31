from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass

from src.sales_agent.services.domain_config import load_domain_config


@dataclass(frozen=True)
class StageDefinition:
    name: str
    crm_id: str
    display: str
    summary: str


_STAGES: tuple[StageDefinition, ...] | None = None


def _ensure_stages_loaded():
    global _STAGES
    if _STAGES is None:
        cfg = load_domain_config()
        _STAGES = tuple(
            StageDefinition(name=s.name, crm_id=s.crm_id, display=s.display, summary=s.summary) for s in cfg.stages
        )
    return _STAGES


def stages() -> Iterable[StageDefinition]:
    return _ensure_stages_loaded()


def resolve_stage(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None

    stages_tuple = _ensure_stages_loaded()
    stage_map = {stage.name: stage.name for stage in stages_tuple}
    stage_reverse_map = {stage.crm_id: stage.name for stage in stages_tuple}

    upper = normalized.upper()
    if upper in stage_map:
        return upper
    return stage_reverse_map.get(upper)


def to_crm_stage(stage_name: str | None) -> str | None:
    if not stage_name:
        return None

    stages_tuple = _ensure_stages_loaded()
    stage_map = {stage.name: stage.crm_id for stage in stages_tuple}
    stage_reverse_map = {stage.crm_id: stage.crm_id for stage in stages_tuple}

    if stage_name in stage_map:
        return stage_map[stage_name]
    if stage_name in stage_reverse_map:
        return stage_name
    return None


def build_stage_rules(current_stage: str | None) -> str:
    stages_tuple = _ensure_stages_loaded()

    payload = {
        "current_stage": current_stage,
        "stages": [
            {
                "id": stage.name,
                "crm_id": stage.crm_id,
                "display": stage.display,
                "summary": stage.summary,
                "is_current": stage.name == current_stage,
            }
            for stage in stages_tuple
        ],
        "guidelines": [
            "Меняй стадию только при подтверждённых данных клиента.",
            "Для смены стадии используй тулзу update_stage с параметрами thread_id и stage.",
        ],
    }
    return json.dumps(payload, ensure_ascii=False)
