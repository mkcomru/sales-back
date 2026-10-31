from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.sales_agent.services.company_context import get_company_spec


@dataclass(frozen=True)
class StageCfg:
    name: str
    crm_id: str
    display: str
    summary: str


@dataclass(frozen=True)
class DomainConfig:
    stages: list[StageCfg]
    category_rules: list[dict[str, Any]]  # AICODE-NOTE: Renamed from product_rules
    tools_qualifier: list[str]
    crm_default_stage_id: str
    crm_forward_metadata_keys: list[str]
    crm_manager_attention_stage_id: str


def load_domain_config() -> DomainConfig:
    """Load from backend spec (via context)."""
    spec = get_company_spec()
    stages_raw = spec.get("stages_config") or []
    stages = [
        StageCfg(
            name=str(item.get("name")),
            crm_id=str(item.get("crm_id")),
            display=str(item.get("display") or ""),
            summary=str(item.get("summary") or ""),
        )
        for item in stages_raw
        if item and item.get("name") and item.get("crm_id")
    ]

    # Tools компании для qualifier (берутся из БД через company_tools)
    company_tools = spec.get("tools") or []
    tools_qualifier = [tool.get("name") for tool in company_tools if tool.get("name")]

    return DomainConfig(
        stages=stages,
        category_rules=spec.get("category_rules") or [],
        tools_qualifier=tools_qualifier,
        crm_default_stage_id=spec.get("crm_default_stage_id", "PROCESSED"),
        crm_forward_metadata_keys=spec.get("crm_forward_metadata_keys") or [],
        crm_manager_attention_stage_id=(
            spec.get("crm_manager_attention_stage_id") or spec.get("crm_default_stage_id", "PROCESSED")
        ),
    )


def rule_match(answers: dict[str, Any], rule: dict[str, Any]) -> bool:
    """Match a single rule from domain config.

    Supported structure:
    - { when: { all_of: [ {key, equals|op|in, ...}, ... ] }, product_id: int }
    - { when: { any_of: [ {key, equals|op|in, ...}, ... ] }, product_id: int }
    - Entry forms supported:
        * { key, equals: value }
        * { key, in: [v1, v2, ...] }
        * { key, op: gt|gte|lt|lte, value: number }
    """
    cond = rule.get("when") or {}
    all_of = cond.get("all_of") or []
    any_of = cond.get("any_of") or []

    def _to_number(x: Any) -> float | None:
        if isinstance(x, int | float):
            return float(x)
        try:
            # allow numeric strings and comma decimal separator
            s = str(x).strip().replace(",", ".")
            return float(s)
        except Exception:
            return None

    def _normalize_str(val: Any) -> str | None:
        """Normalize string for case-insensitive comparison."""
        if val is None:
            return None
        if isinstance(val, str):
            return val.lower().strip()
        return str(val).lower().strip()

    def _compare(op: str, left: Any, right: Any) -> bool:
        op = (op or "").lower()
        if op in {"gt", "gte", "lt", "lte"}:
            a = _to_number(left)
            b = _to_number(right)
            if a is None or b is None:
                return False
            if op == "gt":
                return a > b
            if op == "gte":
                return a >= b
            if op == "lt":
                return a < b
            if op == "lte":
                return a <= b
            return False
        if op == "in":
            if isinstance(right, list | tuple | set):
                # Case-insensitive check for strings
                left_norm = _normalize_str(left)
                for item in right:
                    if _normalize_str(item) == left_norm:
                        return True
                return False
            return False
        # equals / default — case-insensitive for strings
        if isinstance(left, str) and isinstance(right, str):
            return _normalize_str(left) == _normalize_str(right)
        return left == right

    def _check(entry: dict[str, Any]) -> bool:
        key = entry.get("key")
        if not key:
            return False
        val = answers.get(key)

        if "equals" in entry:
            return _compare("equals", val, entry.get("equals"))
        if "in" in entry:
            return _compare("in", val, entry.get("in"))

        op = entry.get("op")
        if op:
            return _compare(str(op), val, entry.get("value"))

        # fallback: treat {key, value} as equals if provided
        if "value" in entry:
            return _compare("equals", val, entry.get("value"))
        return False

    if all_of:
        if not all(_check(e) for e in all_of):
            return False
    if any_of:
        if not any(_check(e) for e in any_of):
            return False
    return True


def category_id_from_answers(answers: dict[str, Any] | None) -> int | None:
    """Determine category_id from customer answers using category_rules.

    Args:
        answers: Customer answers dict

    Returns:
        category_id if rules match, None otherwise
    """
    cfg = load_domain_config()
    if not answers:
        return None

    for rule in cfg.category_rules:
        if rule_match(answers, rule):
            category_id = rule.get("category_id")
            if isinstance(category_id, int):
                return category_id
            if isinstance(category_id, str):
                try:
                    return int(category_id)
                except ValueError:
                    pass

    return None
