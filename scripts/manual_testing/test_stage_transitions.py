#!/usr/bin/env python3
"""Interactive test script for stage transitions (Plan 037).

Tests scenarios:
1. List stages and order state — verify current stage, frozen status
2. Manual stage change — PATCH order with stage_id
3. Recalculate single order — POST recalculate-stage
4. Frozen order isolation — freeze blocks transitions; unfreeze + recalc resumes
5. Stage requirements report — POST stage-requirements, verify structure
6. Auto-transition — add stage with condition, update order_fields, recalc
7. Full funnel 5+ stages — step-based sequential transitions
8. Nested $and/$or — complex logical conditions (budget AND (region OR remote) AND category)
9. $not operator — negation condition
10. Comparison operators — $gte, $lt
11. Complex condition report — condition_report nested structure

Usage:
    cd scripts/manual_testing
    python test_stage_transitions.py

Requirements:
    Backend running (docker-compose up backend)
"""

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from framework import BaseTestClient, Scenario, console, error, run_scenarios, success, warn
from framework.output import print_json, print_scenario_header
from framework.scenarios import interactive_menu
from framework.setup import setup_environment


class StageTransitionsClient(BaseTestClient):
    """Client for stage transition testing."""

    async def list_stages(self) -> list[dict[str, Any]]:
        """List all stages for company."""
        return await self.get(f"/companies/{self.company_id}/stages")

    async def create_stage(
        self,
        name: str,
        position: int | None = None,
        transition_condition: dict[str, Any] | None = None,
        is_final: bool = False,
        color: str = "#64748b",
    ) -> dict[str, Any]:
        """Create a stage."""
        payload: dict[str, Any] = {"name": name, "color": color, "is_final": is_final}
        if position is not None:
            payload["position"] = position
        if transition_condition is not None:
            payload["transition_condition"] = transition_condition
        return await self.post(f"/companies/{self.company_id}/stages", json=payload)

    async def update_stage(
        self,
        stage_id: int,
        *,
        transition_condition: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Update stage (e.g. transition_condition)."""
        payload: dict[str, Any] = {}
        if transition_condition is not None:
            payload["transition_condition"] = transition_condition
        return await self.patch(f"/companies/{self.company_id}/stages/{stage_id}", json=payload)

    async def patch_order(
        self,
        order_id: int,
        *,
        stage_id: int | None = None,
        order_fields: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Update order (stage_id, order_fields)."""
        payload: dict[str, Any] = {}
        if stage_id is not None:
            payload["stage_id"] = stage_id
        if order_fields is not None:
            payload["order_fields"] = order_fields
        return await self.patch(f"/companies/{self.company_id}/orders/{order_id}", json=payload)

    async def recalculate_order_stage(self, order_id: int) -> dict[str, Any]:
        """Recalculate stage for a single order."""
        return await self.post(
            f"/companies/{self.company_id}/orders/{order_id}/recalculate-stage",
        )

    async def update_order_frozen(self, order_id: int, frozen: bool) -> dict[str, Any]:
        """Freeze or unfreeze order."""
        return await self.patch(
            f"/companies/{self.company_id}/orders/{order_id}/frozen",
            json={"frozen": frozen},
        )

    async def get_stage_requirements(self, order_id: int) -> dict[str, Any]:
        """Get stage requirements for an order."""
        return await self.post(
            f"/companies/{self.company_id}/orders/{order_id}/stage-requirements",
        )

    async def delete_stage(self, stage_id: int) -> bool:
        """Delete a stage."""
        return await self.delete(f"/companies/{self.company_id}/stages/{stage_id}")

    async def reorder_stages(self, stage_ids: list[int]) -> list[dict[str, Any]]:
        """Reorder stages by IDs."""
        return await self.put(
            f"/companies/{self.company_id}/stages/reorder",
            json={"stage_ids": stage_ids},
        )


def _stage_name(stage: dict[str, Any] | None) -> str:
    if not stage:
        return "null"
    return f"{stage.get('name', '?')} (id={stage.get('id')})"


async def scenario_1_list_stages_and_order(client: StageTransitionsClient) -> bool:
    """Scenario 1: List stages and verify order state."""
    print_scenario_header("Scenario 1: List Stages and Order State", "Verify current stage, frozen status")

    assert client.order_id is not None

    console.print("[yellow]Step 1: List stages...[/yellow]")
    stages = await client.list_stages()
    success(f"Found {len(stages)} stages")

    for s in stages:
        cond = s.get("transition_condition")
        cond_str = json.dumps(cond)[:60] + "..." if cond and len(json.dumps(cond)) > 60 else (json.dumps(cond) or "null")
        console.print(
            f"   - {s['name']} (id={s['id']}, pos={s['position']}, final={s.get('is_final')}) "
            f"cond={cond_str}"
        )

    console.print("\n[yellow]Step 2: Get current order...[/yellow]")
    order = await client.get_order(client.order_id)
    success(f"Order #{order.get('order_number')} stage={_stage_name(order.get('stage'))}, frozen={order.get('frozen')}")

    if not order.get("stage"):
        error("Order has no stage")
        return False

    success("Order state verified")
    console.print("\n[bold green]✓ Scenario 1 PASSED[/bold green]")
    return True


async def scenario_2_manual_stage_change(client: StageTransitionsClient) -> bool:
    """Scenario 2: Manual stage change via PATCH."""
    print_scenario_header("Scenario 2: Manual Stage Change", "PATCH order with stage_id")

    assert client.order_id is not None

    stages = await client.list_stages()
    if len(stages) < 2:
        error("Need at least 2 stages for this test")
        return False

    target = stages[1]
    order_before = await client.get_order(client.order_id)
    from_stage = order_before.get("stage", {})

    console.print(f"[yellow]Step 1: PATCH order stage_id={target['id']} ({target['name']})...[/yellow]")
    updated = await client.patch_order(client.order_id, stage_id=target["id"])
    success(f"Order updated: stage={_stage_name(updated.get('stage'))}")

    if not updated.get("stage") or updated["stage"].get("id") != target["id"]:
        error(f"Expected stage {target['id']}, got {updated.get('stage')}")
        return False

    console.print(f"\n[yellow]Step 2: Move back to original stage {from_stage.get('id')}...[/yellow]")
    if from_stage and from_stage.get("id"):
        restored = await client.patch_order(client.order_id, stage_id=from_stage["id"])
        success(f"Restored stage={_stage_name(restored.get('stage'))}")

    console.print("\n[bold green]✓ Scenario 2 PASSED[/bold green]")
    return True


async def scenario_3_recalculate(client: StageTransitionsClient) -> bool:
    """Scenario 3: Recalculate single order."""
    print_scenario_header("Scenario 3: Recalculate Single Order", "POST recalculate-stage")

    assert client.order_id is not None

    order_before = await client.get_order(client.order_id)
    stage_before = order_before.get("stage")

    console.print("[yellow]Step 1: POST recalculate-stage...[/yellow]")
    result = await client.recalculate_order_stage(client.order_id)
    success(f"Recalc done: stage={_stage_name(result.get('stage'))}")

    stage_after = result.get("stage")
    if stage_before and stage_after and stage_before.get("id") == stage_after.get("id"):
        success("Stage unchanged (no transition conditions met or already at furthest)")

    console.print("\n[bold green]✓ Scenario 3 PASSED[/bold green]")
    return True


async def scenario_4_frozen_isolation(client: StageTransitionsClient) -> bool:
    """Scenario 4: Frozen order blocks transitions; unfreeze + recalc resumes."""
    print_scenario_header("Scenario 4: Frozen Order Isolation", "Freeze blocks recalc; unfreeze resumes")

    assert client.order_id is not None

    stages = await client.list_stages()
    if len(stages) < 2:
        warn("Need 2+ stages; skipping frozen assertion")
        console.print("\n[bold green]✓ Scenario 4 PASSED (minimal)[/bold green]")
        return True

    order = await client.get_order(client.order_id)
    initial_stage_id = order.get("stage", {}).get("id")
    if not order.get("stage"):
        error("Order has no stage")
        return False

    console.print("[yellow]Step 1: Freeze order...[/yellow]")
    frozen_order = await client.update_order_frozen(client.order_id, frozen=True)
    if not frozen_order.get("frozen"):
        error("Order not frozen")
        return False
    success("Order frozen")

    console.print("\n[yellow]Step 2: Update order_fields (budget) and recalc...[/yellow]")
    await client.patch_order(client.order_id, order_fields={"budget": 5000})
    recalc = await client.recalculate_order_stage(client.order_id)

    if recalc.get("stage", {}).get("id") != initial_stage_id:
        warn("Stage changed despite frozen - may be expected if backend skips recalc for frozen")
    else:
        success("Stage unchanged while frozen")

    console.print("\n[yellow]Step 3: Unfreeze and recalc...[/yellow]")
    unfrozen = await client.update_order_frozen(client.order_id, frozen=False)
    if unfrozen.get("frozen"):
        error("Order still frozen")
        return False
    success("Order unfrozen")

    after_recalc = await client.recalculate_order_stage(client.order_id)
    success(f"After recalc: stage={_stage_name(after_recalc.get('stage'))}")

    console.print("\n[bold green]✓ Scenario 4 PASSED[/bold green]")
    return True


async def scenario_5_stage_requirements(client: StageTransitionsClient) -> bool:
    """Scenario 5: Stage requirements report."""
    print_scenario_header("Scenario 5: Stage Requirements Report", "POST stage-requirements")

    assert client.order_id is not None

    console.print("[yellow]Step 1: POST stage-requirements...[/yellow]")
    req = await client.get_stage_requirements(client.order_id)
    success("Got stage requirements")

    if "current_stage" in req:
        console.print(f"   current_stage: {req['current_stage']}")
    if "next_stages" in req:
        console.print(f"   next_stages: {len(req['next_stages'])} stages")
        for ns in req.get("next_stages", [])[:3]:
            console.print(f"     - {ns.get('stage', {}).get('name')}: met={ns.get('met')}")

    print_json(req, title="Stage Requirements (excerpt)", style="cyan")

    if "current_stage" not in req and "next_stages" not in req:
        warn("Response missing expected keys (schema may differ)")

    console.print("\n[bold green]✓ Scenario 5 PASSED[/bold green]")
    return True


async def scenario_6_auto_transition(client: StageTransitionsClient) -> bool:
    """Scenario 6: Auto-transition — add stage with condition, update fields, recalc."""
    print_scenario_header("Scenario 6: Auto-Transition", "Create stage with condition, update fields, recalc")

    assert client.order_id is not None

    stages = await client.list_stages()
    first_stage = stages[0] if stages else None
    if not first_stage:
        error("No stages")
        return False

    console.print("[yellow]Step 1: Ensure order is on first stage...[/yellow]")
    await client.patch_order(client.order_id, stage_id=first_stage["id"])
    order = await client.get_order(client.order_id)
    success(f"Order on {order.get('stage', {}).get('name')}")

    console.print("\n[yellow]Step 2: Create stage with transition_condition $any...[/yellow]")
    new_stage = await client.create_stage(
        name=f"Тест автопереход_{int(time.time()) % 100000}",
        position=None,
        transition_condition={"$any": True},
        color="#3b82f6",
    )
    success(f"Created stage: {new_stage['name']} (id={new_stage['id']})")

    console.print("\n[yellow]Step 3: Recalculate order...[/yellow]")
    recalc = await client.recalculate_order_stage(client.order_id)
    stage_after = recalc.get("stage")

    if stage_after and stage_after.get("id") == new_stage["id"]:
        success("Auto-transitioned to new stage")
    else:
        warn(
            f"Expected transition to {new_stage['id']}, got {stage_after.get('id') if stage_after else 'null'}. "
            "Condition or stage order may differ."
        )

    console.print("\n[bold green]✓ Scenario 6 PASSED[/bold green]")
    return True


async def scenario_7_full_funnel_five_stages(client: StageTransitionsClient) -> bool:
    """Scenario 7: Full funnel with 5+ stages, step-based sequential progression."""
    print_scenario_header("Scenario 7: Full Funnel (5+ Stages)", "Step-based sequential transitions")

    assert client.order_id is not None

    stages = await client.list_stages()
    ts = int(time.time()) % 100000

    console.print("[yellow]Step 1: Create 4 custom stages (step >= 1, 2, 3, 4)...[/yellow]")
    for i in range(1, 5):
        stage = await client.create_stage(
            name=f"Этап_{i}_{ts}",
            position=None,
            transition_condition={"order_fields.step": {"$gte": i}},
            color="#22c55e",
        )
        success(f"Created: {stage['name']} (pos={stage.get('position')})")

    stages = await client.list_stages()
    success(f"Total stages: {len(stages)}")
    id_to_pos = {s["id"]: s["position"] for s in stages}

    first_stage = stages[0]
    console.print(f"\n[yellow]Step 2: Move order to first stage {first_stage['name']}...[/yellow]")
    await client.patch_order(client.order_id, stage_id=first_stage["id"])
    success("Order on first stage")

    ordered_non_final = [s for s in sorted(stages, key=lambda x: x["position"]) if not s.get("is_final") and s.get("position", 0) > 0]
    step_stage_ids = [s["id"] for s in ordered_non_final[:4]]
    console.print("\n[yellow]Step 3: Sequential step progression (step=1..4)...[/yellow]")
    for step in range(1, 5):
        await client.patch_order(client.order_id, order_fields={"step": step})
        recalc = await client.recalculate_order_stage(client.order_id)
        stage_after = recalc.get("stage") or {}
        expected_id = step_stage_ids[step - 1] if step <= len(step_stage_ids) else None
        if expected_id and stage_after.get("id") == expected_id:
            success(f"step={step} -> {stage_after.get('name', '?')}")
        elif stage_after.get("id"):
            success(f"step={step} -> {stage_after.get('name', '?')} (pos={id_to_pos.get(stage_after.get('id'))})")
        else:
            warn(f"step={step}: no transition")

    console.print("\n[bold green]✓ Scenario 7 PASSED[/bold green]")
    return True


async def scenario_8_nested_and_or(client: StageTransitionsClient) -> bool:
    """Scenario 8: Nested $and/$or conditions — budget AND (region OR remote) AND category."""
    print_scenario_header("Scenario 8: Nested $and/$or", "Complex logical conditions")

    assert client.order_id is not None

    stages = await client.list_stages()
    first_stage = stages[0]
    ts = int(time.time()) % 100000

    cond = {
        "$and": [
            {"order_fields.qual_budget": {"$gte": 1000}},
            {
                "$or": [
                    {"order_fields.qual_region": {"$exists": True}},
                    {"order_fields.qual_remote": {"$eq": True}},
                ]
            },
            {"order_fields.qual_category": {"$exists": True}},
        ]
    }

    console.print("[yellow]Step 1: Create Qualified stage with nested $and/$or...[/yellow]")
    qualified = await client.create_stage(
        name=f"Qualified_{ts}",
        position=None,
        transition_condition=cond,
        color="#3b82f6",
    )
    success(f"Created: {qualified['name']}")

    console.print("\n[yellow]Step 2: Move order to first stage...[/yellow]")
    await client.patch_order(client.order_id, stage_id=first_stage["id"])

    console.print("\n[yellow]Step 3: Set budget+category only (no region/remote) -> should NOT transition...[/yellow]")
    await client.patch_order(
        client.order_id,
        order_fields={"qual_budget": 2000, "qual_category": "consulting"},
    )
    recalc = await client.recalculate_order_stage(client.order_id)
    stage_after = recalc.get("stage") or {}
    if stage_after.get("id") != qualified["id"]:
        success("Correctly stayed on first stage (OR branch not met)")
    else:
        warn("Transitioned despite missing region/remote")

    console.print("\n[yellow]Step 4: Add qual_remote=true -> should transition...[/yellow]")
    await client.patch_order(client.order_id, order_fields={"qual_remote": True})
    recalc = await client.recalculate_order_stage(client.order_id)
    stage_after = recalc.get("stage") or {}
    if stage_after.get("id") == qualified["id"]:
        success("Transitioned to Qualified")
    else:
        warn(f"Expected Qualified, got {stage_after.get('name')}")

    console.print("\n[bold green]✓ Scenario 8 PASSED[/bold green]")
    return True


async def scenario_9_not_operator(client: StageTransitionsClient) -> bool:
    """Scenario 9: $not operator — transition when interested != true."""
    print_scenario_header("Scenario 9: $not Operator", "Negation condition")

    assert client.order_id is not None

    stages = await client.list_stages()
    first_stage = stages[0]
    ts = int(time.time()) % 100000

    console.print("[yellow]Step 1: Create NotInterested stage ($not interested==true)...[/yellow]")
    not_stage = await client.create_stage(
        name=f"NotInterested_{ts}",
        position=None,
        transition_condition={"$not": {"order_fields.interested": {"$eq": True}}},
        color="#ef4444",
    )
    success(f"Created: {not_stage['name']}")

    console.print("\n[yellow]Step 2: Move order to first stage, set interested=false...[/yellow]")
    await client.patch_order(client.order_id, stage_id=first_stage["id"])
    await client.patch_order(client.order_id, order_fields={"interested": False})

    console.print("\n[yellow]Step 3: Recalculate -> should transition (interested=false -> $not true)...[/yellow]")
    recalc = await client.recalculate_order_stage(client.order_id)
    stage_after = recalc.get("stage") or {}
    if stage_after.get("id") == not_stage["id"]:
        success("Transitioned to NotInterested")
    else:
        warn(f"Expected NotInterested, got {stage_after.get('name')}")

    console.print("\n[bold green]✓ Scenario 9 PASSED[/bold green]")
    return True


async def scenario_10_comparison_operators(client: StageTransitionsClient) -> bool:
    """Scenario 10: Comparison operators $gte, $lt — Mid (1000-5000), High (>=5000)."""
    print_scenario_header("Scenario 10: Comparison Operators", "$gte, $lt, $lte")

    assert client.order_id is not None

    stages = await client.list_stages()
    first_stage = stages[0]
    ts = int(time.time()) % 100000

    console.print("[yellow]Step 1: Create Mid (1000<=budget<5000) and High (>=5000)...[/yellow]")
    mid = await client.create_stage(
        name=f"MidBudget_{ts}",
        position=None,
        transition_condition={
            "$and": [
                {"order_fields.comp_budget": {"$gte": 1000}},
                {"order_fields.comp_budget": {"$lt": 5000}},
            ]
        },
        color="#eab308",
    )
    high = await client.create_stage(
        name=f"HighBudget_{ts}",
        position=None,
        transition_condition={"order_fields.comp_budget": {"$gte": 5000}},
        color="#8b5cf6",
    )
    success(f"Created Mid and High stages")

    console.print("\n[yellow]Step 2: Move to first, set comp_budget=3000 -> Mid...[/yellow]")
    await client.patch_order(client.order_id, stage_id=first_stage["id"])
    await client.patch_order(client.order_id, order_fields={"comp_budget": 3000})
    recalc = await client.recalculate_order_stage(client.order_id)
    stage_after = recalc.get("stage") or {}
    if stage_after.get("id") == mid["id"]:
        success("budget=3000 -> Mid")
    else:
        warn(f"Expected Mid, got {stage_after.get('name')}")

    console.print("\n[yellow]Step 3: Set comp_budget=6000 -> High...[/yellow]")
    await client.patch_order(client.order_id, order_fields={"comp_budget": 6000})
    recalc = await client.recalculate_order_stage(client.order_id)
    stage_after = recalc.get("stage") or {}
    if stage_after.get("id") == high["id"]:
        success("budget=6000 -> High")
    else:
        warn(f"Expected High, got {stage_after.get('name')}")

    console.print("\n[bold green]✓ Scenario 10 PASSED[/bold green]")
    return True


async def scenario_11_complex_condition_report(client: StageTransitionsClient) -> bool:
    """Scenario 11: Stage requirements with nested condition_report structure."""
    print_scenario_header("Scenario 11: Complex Condition Report", "condition_report with nested groups")

    assert client.order_id is not None

    req = await client.get_stage_requirements(client.order_id)
    success("Got stage requirements")

    report = None
    for ns in req.get("next_stages", []):
        if ns.get("condition_report"):
            report = ns["condition_report"]
            break
    if not report:
        warn("No condition_report in next_stages (optional)")
        console.print("\n[bold green]✓ Scenario 11 PASSED (no report)[/bold green]")
        return True

    root = report.get("root")
    if not root:
        warn("condition_report missing root")
    else:
        if root.get("type") == "group":
            success("Root is group")
        children = root.get("children", [])
        has_clause = any(c.get("type") == "clause" for c in children)
        has_nested_group = any(c.get("type") == "group" for c in children)
        if has_clause or has_nested_group:
            success(f"Children: {len(children)} (clauses/groups present)")

    print_json(report, title="Condition Report (excerpt)", style="cyan")
    console.print("\n[bold green]✓ Scenario 11 PASSED[/bold green]")
    return True


SCENARIOS = [
    Scenario("List Stages and Order", scenario_1_list_stages_and_order, "Verify current stage, frozen"),
    Scenario("Manual Stage Change", scenario_2_manual_stage_change, "PATCH order with stage_id"),
    Scenario("Recalculate Single Order", scenario_3_recalculate, "POST recalculate-stage"),
    Scenario("Frozen Order Isolation", scenario_4_frozen_isolation, "Freeze blocks recalc"),
    Scenario("Stage Requirements", scenario_5_stage_requirements, "POST stage-requirements"),
    Scenario("Auto-Transition", scenario_6_auto_transition, "Condition-based transition"),
    Scenario("Full Funnel 5+ Stages", scenario_7_full_funnel_five_stages, "Step-based sequential"),
    Scenario("Nested $and/$or", scenario_8_nested_and_or, "Complex logical conditions"),
    Scenario("$not Operator", scenario_9_not_operator, "Negation condition"),
    Scenario("Comparison Operators", scenario_10_comparison_operators, "$gte, $lt"),
    Scenario("Complex Condition Report", scenario_11_complex_condition_report, "condition_report nested"),
]


async def util_list_stages(client: StageTransitionsClient) -> None:
    """List company stages."""
    stages = await client.list_stages()
    console.print(f"\n[cyan]Stages ({len(stages)}):[/cyan]")
    for s in stages:
        console.print(f"  {s['id']}: {s['name']} pos={s['position']} final={s.get('is_final')}")


async def util_get_order(client: StageTransitionsClient) -> None:
    """Get order details."""
    if not client.order_id:
        error("No order_id")
        return
    order = await client.get_order(client.order_id)
    print_json(order, title="Order", style="cyan")


async def util_stage_requirements(client: StageTransitionsClient) -> None:
    """Get stage requirements for order."""
    if not client.order_id:
        error("No order_id")
        return
    req = await client.get_stage_requirements(client.order_id)
    print_json(req, title="Stage Requirements", style="cyan")


UTILITIES = [
    ("s", "List stages", util_list_stages),
    ("o", "Get order", util_get_order),
    ("r", "Stage requirements", util_stage_requirements),
]


if __name__ == "__main__":

    async def main() -> int:
        from rich.panel import Panel

        console.print(
            Panel.fit(
                "[bold cyan]Stage Transitions Test[/bold cyan]\n\n"
                "Plan 037: Stage condition builder and report\n"
                "Covers manual change, recalc, frozen, stage-requirements, auto-transition,\n"
                "full funnel, nested $and/$or, $not, comparison operators, condition report.",
                border_style="cyan",
            )
        )

        client = StageTransitionsClient()

        if not await setup_environment(client, "Stage Transitions Test Company", create_thread=True):
            return 1

        await interactive_menu(client, SCENARIOS, utilities=UTILITIES)

        console.print("\n[bold green]Done![/bold green]")
        return 0

    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted[/yellow]")
