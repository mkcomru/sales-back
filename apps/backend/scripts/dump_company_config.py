#!/usr/bin/env python3
"""Dump and restore company configuration between environments.

Exports all configuration entities (categories, fields, stages, prompts, etc.)
excluding transactional data (messages, orders, customers, threads).

IDs are NOT preserved — only the structure and content matter.
FK references are resolved via old→new ID mapping during restore.

Usage:
    cd apps/backend
    uv run python -m scripts.dump_company_config dump <company_id>
    uv run python -m scripts.dump_company_config restore <path_to_dump.json> [--company-name "New Name"]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.backend.modules.categories.models import Category
from src.backend.modules.companies.models import FAQ, Company
from src.backend.modules.core.database import close, init
from src.backend.modules.fields.models import Field, FieldOption
from src.backend.modules.forms.models import FormTemplate, FormTemplateField
from src.backend.modules.products.models import Product
from src.backend.modules.prompt_addon.models import PromptAddon
from src.backend.modules.stages.models import StageTemplate

_backend_dir = Path(__file__).resolve().parent.parent
DUMPS_DIR = _backend_dir.parent.parent / "company_dumps"

COMPANY_FIELDS = [
    "name",
    "description",
    "rules",
    "tone_of_voice",
    "assistant_name",
    "qualification_workflow",
    "qualification_examples",
    "collection_name",
    "stages_config",
    "category_rules",
    "enabled_tools",
    "crm_forward_metadata_keys",
    "crm_default_stage_id",
    "crm_manager_attention_stage_id",
]

CATEGORY_FIELDS = ["name", "description", "rules", "examples", "workflow", "enabled_tools"]

PRODUCT_FIELDS = ["name", "description", "attributes"]

FIELD_FIELDS = ["name", "question", "answer_type", "required", "display_name", "level", "is_system"]

FIELD_OPTION_FIELDS = ["value", "order"]

STAGE_TEMPLATE_FIELDS = [
    "name",
    "color",
    "position",
    "is_final",
    "result",
    "auto_close",
    "transition_condition",
    "is_system",
]

FAQ_FIELDS = ["category", "question", "answer", "keywords"]

PROMPT_ADDON_FIELDS = ["name", "qualification_workflow", "qualification_examples"]

FORM_TEMPLATE_FIELDS = ["name", "enabled"]


def _serialize(obj: Any) -> Any:
    if isinstance(obj, datetime):
        return obj.isoformat()
    if hasattr(obj, "value"):
        return obj.value
    return obj


def _extract(instance: Any, field_names: list[str]) -> dict[str, Any]:
    return {f: _serialize(getattr(instance, f)) for f in field_names}


def _print(tag: str, msg: str) -> None:
    print(f"[{tag}] {msg}")


# ── Dump ─────────────────────────────────────────────────────────────────


async def dump_company(company_id: int) -> dict[str, Any]:
    company = await Company.filter(id=company_id).first()
    if not company:
        _print("ERROR", f"Company {company_id} not found")
        sys.exit(1)

    _print("INFO", f"Dumping company '{company.name}' (id={company_id})")
    payload: dict[str, Any] = {
        "version": 1,
        "source_company_id": company_id,
        "exported_at": datetime.now(UTC).isoformat(),
        "company": _extract(company, COMPANY_FIELDS),
    }

    categories = await Category.filter(company_id=company_id).all()
    payload["categories"] = [{"_id": c.id, **_extract(c, CATEGORY_FIELDS)} for c in categories]
    _print("INFO", f"  categories: {len(categories)}")

    category_ids = [c.id for c in categories]
    products = await Product.filter(category_id__in=category_ids).all() if category_ids else []
    # AICODE-NOTE: Products without category are not company-scoped in the schema,
    # so we only dump products that belong to this company's categories.
    payload["products"] = [
        {"_id": p.id, "_category_id": p.category_id, **_extract(p, PRODUCT_FIELDS)} for p in products
    ]
    _print("INFO", f"  products: {len(products)}")

    fields = await Field.filter(company_id=company_id).all()
    payload["fields"] = [
        {
            "_id": f.id,
            "_category_id": f.category_id,
            "_product_id": f.product_id,
            **_extract(f, FIELD_FIELDS),
        }
        for f in fields
    ]
    _print("INFO", f"  fields: {len(fields)}")

    field_ids = [f.id for f in fields]
    options = await FieldOption.filter(field_id__in=field_ids).all() if field_ids else []
    payload["field_options"] = [{"_field_id": o.field_id, **_extract(o, FIELD_OPTION_FIELDS)} for o in options]
    _print("INFO", f"  field_options: {len(options)}")

    stages = await StageTemplate.filter(company_id=company_id).order_by("position").all()
    payload["stage_templates"] = [{"_id": s.id, **_extract(s, STAGE_TEMPLATE_FIELDS)} for s in stages]
    _print("INFO", f"  stage_templates: {len(stages)}")

    faqs = await FAQ.filter(company_id=company_id).all()
    payload["faqs"] = [_extract(f, FAQ_FIELDS) for f in faqs]
    _print("INFO", f"  faqs: {len(faqs)}")

    addons = await PromptAddon.filter(company_id=company_id).all()
    payload["prompt_addons"] = [{"_id": a.id, **_extract(a, PROMPT_ADDON_FIELDS)} for a in addons]
    _print("INFO", f"  prompt_addons: {len(addons)}")

    form_templates = await FormTemplate.filter(company_id=company_id).all()
    payload["form_templates"] = [
        {"_id": ft.id, "_contact_field_id": ft.contact_field_id, **_extract(ft, FORM_TEMPLATE_FIELDS)}
        for ft in form_templates
    ]
    _print("INFO", f"  form_templates: {len(form_templates)}")

    ft_ids = [ft.id for ft in form_templates]
    ft_fields = await FormTemplateField.filter(form_template_id__in=ft_ids).all() if ft_ids else []
    payload["form_template_fields"] = [
        {
            "_form_template_id": ftf.form_template_id,
            "_field_id": ftf.field_id,
            "position": ftf.position,
        }
        for ftf in ft_fields
    ]
    _print("INFO", f"  form_template_fields: {len(ft_fields)}")

    return payload


async def do_dump(company_id: int) -> None:
    await init()
    try:
        payload = await dump_company(company_id)

        DUMPS_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        filename = f"company_{company_id}_{ts}.json"
        filepath = DUMPS_DIR / filename

        filepath.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
        _print("OK", f"Dump saved to {filepath}")
    finally:
        await close()


# ── Restore ──────────────────────────────────────────────────────────────


async def restore_company(data: dict[str, Any], company_name: str | None) -> int:
    company_data = data["company"].copy()
    if company_name:
        company_data["name"] = company_name

    company_data["collection_name"] = f"col_{uuid.uuid4().hex[:12]}"

    company = await Company.create(**company_data)
    _print("OK", f"Created company '{company.name}' (id={company.id})")

    # ── categories ───────────────────────────────────────────────────
    cat_id_map: dict[int, int] = {}
    for cat in data.get("categories", []):
        orig_id = cat.pop("_id")
        created_cat = await Category.create(company=company, **cat)
        cat_id_map[orig_id] = created_cat.id
    _print("INFO", f"  categories: {len(cat_id_map)}")

    # ── products ─────────────────────────────────────────────────────
    prod_id_map: dict[int, int] = {}
    for prod in data.get("products", []):
        orig_id = prod.pop("_id")
        orig_cat_id = prod.pop("_category_id")
        created_prod = await Product.create(category_id=cat_id_map.get(orig_cat_id), **prod)
        prod_id_map[orig_id] = created_prod.id
    _print("INFO", f"  products: {len(prod_id_map)}")

    # ── fields ───────────────────────────────────────────────────────
    field_id_map: dict[int, int] = {}
    for fld in data.get("fields", []):
        orig_id = fld.pop("_id")
        orig_cat_id = fld.pop("_category_id")
        orig_prod_id = fld.pop("_product_id")
        created_field = await Field.create(
            company=company,
            category_id=cat_id_map.get(orig_cat_id) if orig_cat_id else None,
            product_id=prod_id_map.get(orig_prod_id) if orig_prod_id else None,
            **fld,
        )
        field_id_map[orig_id] = created_field.id
    _print("INFO", f"  fields: {len(field_id_map)}")

    # ── field options ────────────────────────────────────────────────
    opt_count = 0
    for opt in data.get("field_options", []):
        orig_field_id = opt.pop("_field_id")
        new_field_id = field_id_map.get(orig_field_id)
        if new_field_id is None:
            _print("WARN", f"  Skipping field option — source field {orig_field_id} not mapped")
            continue
        await FieldOption.create(field_id=new_field_id, **opt)
        opt_count += 1
    _print("INFO", f"  field_options: {opt_count}")

    # ── stage templates ──────────────────────────────────────────────
    stage_id_map: dict[int, int] = {}
    for stg in data.get("stage_templates", []):
        orig_id = stg.pop("_id")
        created_stage = await StageTemplate.create(company=company, **stg)
        stage_id_map[orig_id] = created_stage.id
    _print("INFO", f"  stage_templates: {len(stage_id_map)}")

    # ── FAQs ─────────────────────────────────────────────────────────
    faq_count = 0
    for faq in data.get("faqs", []):
        await FAQ.create(company=company, **faq)
        faq_count += 1
    _print("INFO", f"  faqs: {faq_count}")

    # ── prompt addons ────────────────────────────────────────────────
    addon_id_map: dict[int, int] = {}
    for addon in data.get("prompt_addons", []):
        orig_id = addon.pop("_id")
        created_addon = await PromptAddon.create(company=company, **addon)
        addon_id_map[orig_id] = created_addon.id
    _print("INFO", f"  prompt_addons: {len(addon_id_map)}")

    # ── form templates ───────────────────────────────────────────────
    ft_id_map: dict[int, int] = {}
    for ft in data.get("form_templates", []):
        orig_id = ft.pop("_id")
        orig_contact_field_id = ft.pop("_contact_field_id")
        new_contact_field_id = field_id_map.get(orig_contact_field_id)
        if new_contact_field_id is None:
            _print(
                "WARN",
                f"  Skipping form template '{ft.get('name')}' — contact field {orig_contact_field_id} not mapped",
            )
            continue
        created_ft = await FormTemplate.create(company=company, contact_field_id=new_contact_field_id, **ft)
        ft_id_map[orig_id] = created_ft.id
    _print("INFO", f"  form_templates: {len(ft_id_map)}")

    # ── form template fields ─────────────────────────────────────────
    ftf_count = 0
    for ftf in data.get("form_template_fields", []):
        new_ft_id = ft_id_map.get(ftf["_form_template_id"])
        new_field_id = field_id_map.get(ftf["_field_id"])
        if new_ft_id is None or new_field_id is None:
            _print("WARN", "  Skipping form template field — unresolved FK")
            continue
        await FormTemplateField.create(form_template_id=new_ft_id, field_id=new_field_id, position=ftf["position"])
        ftf_count += 1
    _print("INFO", f"  form_template_fields: {ftf_count}")

    return company.id


async def do_restore(dump_path: str, company_name: str | None) -> None:
    path = Path(dump_path)
    if not path.exists():
        _print("ERROR", f"File not found: {path}")
        sys.exit(1)

    data = json.loads(path.read_text())
    if data.get("version") != 1:
        _print("ERROR", f"Unsupported dump version: {data.get('version')}")
        sys.exit(1)

    _print(
        "INFO",
        f"Restoring from {path.name} (source company {data['source_company_id']}, exported {data['exported_at']})",
    )

    await init()
    try:
        new_id = await restore_company(data, company_name)
        _print("OK", f"Restore complete. New company id: {new_id}")
    finally:
        await close()


# ── CLI ──────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="Dump / restore company configuration")
    sub = parser.add_subparsers(dest="command", required=True)

    dump_parser = sub.add_parser("dump", help="Export company config to JSON")
    dump_parser.add_argument("company_id", type=int)

    restore_parser = sub.add_parser("restore", help="Import company config from JSON")
    restore_parser.add_argument("dump_file", help="Path to dump JSON file")
    restore_parser.add_argument("--company-name", help="Override company name on restore")

    args = parser.parse_args()

    match args.command:
        case "dump":
            asyncio.run(do_dump(args.company_id))
        case "restore":
            asyncio.run(do_restore(args.dump_file, args.company_name))


if __name__ == "__main__":
    main()
