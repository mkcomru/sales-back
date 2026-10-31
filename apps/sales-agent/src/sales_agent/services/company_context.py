"""Request-scoped context for stateless pipeline.

Stores envelope data in ContextVars so tools can access it
without extra read calls to the backend.
"""

from contextvars import ContextVar
from typing import Any

_company_spec: ContextVar[dict[str, Any] | None] = ContextVar("company_spec", default=None)
_customer_answers: ContextVar[dict[str, Any] | None] = ContextVar("customer_answers", default=None)
_order_fields: ContextVar[dict[str, Any] | None] = ContextVar("order_fields", default=None)
_extra_fields: ContextVar[dict[str, Any] | None] = ContextVar("extra_fields", default=None)
_handoff_result: ContextVar[dict[str, Any] | None] = ContextVar("handoff_result", default=None)


def set_company_spec(spec: dict[str, Any]) -> None:
    _company_spec.set(spec)


def get_company_spec() -> dict[str, Any]:
    spec = _company_spec.get()
    if spec is None:
        raise RuntimeError("Company spec not loaded")
    return spec


def set_customer_answers(answers: dict[str, Any]) -> None:
    _customer_answers.set(answers)


def get_customer_answers() -> dict[str, Any]:
    answers = _customer_answers.get()
    if answers is None:
        raise RuntimeError("Customer answers not loaded")
    return answers


def set_order_fields(fields: dict[str, Any]) -> None:
    _order_fields.set(fields)


def get_order_fields() -> dict[str, Any]:
    return _order_fields.get() or {}


def set_extra_fields(fields: dict[str, Any]) -> None:
    _extra_fields.set(fields)


def get_extra_fields() -> dict[str, Any]:
    return _extra_fields.get() or {}


def set_handoff_result(data: dict[str, Any]) -> None:
    _handoff_result.set(data)


def get_handoff_result() -> dict[str, Any] | None:
    return _handoff_result.get()


def reset_request_context() -> None:
    _company_spec.set(None)
    _customer_answers.set(None)
    _order_fields.set(None)
    _extra_fields.set(None)
    _handoff_result.set(None)
