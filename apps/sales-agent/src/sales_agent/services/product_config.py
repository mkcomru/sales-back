from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationInfo, field_validator

from src.sales_agent.services.company_context import get_company_spec

PRODUCTS_DIR = Path(__file__).resolve().parents[1] / "agents" / "products"
FieldType = Literal["enum", "int", "number", "money", "union", "string"]


class FieldSpec(BaseModel):
    key: str
    type: FieldType
    title: str
    description: str | None = None
    enum: list[str] | None = None
    min: float | int | None = None
    max: float | int | None = None
    unit: str | None = None
    one_of: list[FieldSpec] | None = None

    @field_validator("enum")
    @classmethod
    def _enum_only_for_enum(cls, v: Any, info: ValidationInfo):  # type: ignore[override]
        data = info.data or {}
        if v is not None and data.get("type") != "enum":
            raise ValueError("'enum' is allowed only for type=='enum'")
        return v

    @field_validator("one_of")
    @classmethod
    def _one_of_only_for_union(cls, v: Any, info: ValidationInfo):  # type: ignore[override]
        data = info.data or {}
        if v is not None and data.get("type") != "union":
            raise ValueError("'one_of' is allowed only for type=='union'")
        return v


class FieldsConfig(BaseModel):
    fields: list[FieldSpec] = Field(default_factory=list)


class ProductConfig(BaseModel):
    product: int
    fields: FieldsConfig = Field(default_factory=FieldsConfig)
    messages: dict[str, str] = Field(default_factory=dict)


def load_product_config(product_id: int) -> ProductConfig:
    """Load from backend spec (via context)."""
    spec = get_company_spec()
    products = spec.get("products") or []
    product = next((p for p in products if p.get("id") == product_id), None)

    if not product:
        raise ValueError(f"Product {product_id} not found")

    all_fields = spec.get("fields") or []
    product_fields = [f for f in all_fields if f.get("product_id") == product_id]

    field_specs = []
    for f in product_fields:
        field_type = f.get("type", "string")
        field_spec: dict[str, Any] = {
            "key": f.get("name", ""),
            "type": field_type,
            "title": f.get("question", ""),
            "description": None,
        }

        if field_type == "enum":
            options = f.get("options", [])
            field_spec["enum"] = [opt.get("value", "") for opt in options]

        field_specs.append(FieldSpec.model_validate(field_spec))

    return ProductConfig(
        product=product_id,
        fields=FieldsConfig(fields=field_specs),
        messages={},
    )


def load_product_profile(product_id: int) -> str:
    """Load from backend spec (via context)."""
    spec = get_company_spec()
    products = spec.get("products") or []
    product = next((p for p in products if p.get("id") == product_id), None)

    if not product:
        return ""

    parts = []
    if product.get("description"):
        parts.append(product["description"])
    if product.get("guidelines"):
        parts.append(product["guidelines"])
    return "\n\n".join(parts)


def load_product_catalog() -> str:
    """Load from backend spec (via context)."""
    spec = get_company_spec()
    products = spec.get("products") or []

    lines = ["# Каталог продуктов\n"]
    for product in products:
        lines.append(f"## {product.get('name', 'Unnamed')}")
        lines.append(f"**ID**: {product.get('id', 'N/A')}")
        if product.get("description"):
            lines.append(f"\n{product['description']}")
        lines.append("")
    return "\n".join(lines)


def product_config_json(product_id: int) -> str:
    cfg = load_product_config(product_id)
    return json.dumps(cfg.model_dump(), ensure_ascii=False)
