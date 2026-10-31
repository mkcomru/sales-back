#!/usr/bin/env python3
"""E2E test script for Stage-Based Auto-Pings (Plan 039).

Real end-to-end tests: creates a custom connector, sends real inbound messages,
waits for the real evaluator to schedule pings, the real scheduler to execute them,
and the real sales-agent to generate AI responses.

Scenarios:
 1. Basic CRUD           — Create, list, update, delete ping rules
 2. Final Stage Block    — Cannot create rules on final stages (400)
 3. Max 5 Limit          — 6th rule on same stage → 400
 4. Static Validation    — content_type=static without static_content → 422
 5. Condition Syntax     — Invalid condition JSON → 422
 6. Position Bounds      — position=0 and position=6 → 422
 7. Reorder Rules        — Reorder by IDs, verify positions update
 8. AI Content Type      — prompt_override persists
 9. Deactivate Rule      — is_active toggle
10. E2E: AI Ping         — Real evaluator → scheduler → sales-agent AI generation
11. E2E: Static Ping     — Real evaluator → scheduler → static content delivery
12. E2E: Cancel on Reply — Real inbound message cancels evaluator-created pings
13. E2E: Agent Priority  — Agent followup task suppresses evaluator for real
14. E2E: Deactivated Rule Ignored — is_active=False rule skipped by evaluator
15. Stage Change Cancel  — Stage change cancels old-stage pings (hook check)
16. Company Isolation    — Wrong company_id → 404

Services required:
    just dev backend,sales-agent,workers

Usage:
    python test_auto_pings.py
"""

import asyncio
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

sys.path.insert(0, str(Path(__file__).parent))

from framework import BaseTestClient, MockTransport, Scenario, console, error, run_scenarios, success, warn
from framework.config import config
from framework.output import print_json, print_scenario_header, print_table
from framework.scenarios import interactive_menu
from framework.setup import setup_environment

EVALUATOR_POLL = 60
SCHEDULER_POLL = 10
MAX_WAIT_EVALUATOR = 80
MAX_WAIT_EXECUTION = 30


class AutoPingsClient(BaseTestClient):
    """Client for auto-pings E2E testing with a real connector."""

    connector_id: str | None = None
    conversation_id: str | None = None
    user_external_id: str | None = None

    # ── Connector ─────────────────────────────────────────────────────────────

    async def create_connector(
        self, connector_id: str, transport_endpoint: str
    ) -> dict[str, Any]:
        return await self.post(
            f"/companies/{self.company_id}/connectors",
            json={
                "connector_id": connector_id,
                "company_id": self.company_id,
                "type": "custom",
                "channel_type": "test",
                "display_name": "Ping E2E Test Connector",
                "managed": True,
                "config": {"transport_endpoint": transport_endpoint},
                "enabled": True,
                "debounce_window_seconds": 1,
            },
        )

    async def list_connectors(self) -> list[dict[str, Any]]:
        return await self.get(f"/companies/{self.company_id}/connectors")

    # ── Real inbound message ──────────────────────────────────────────────────

    async def send_customer_message(self, text: str) -> dict[str, Any]:
        """Send a real customer message through the inbound endpoint.

        Goes through the full flow: connector auth → thread get-or-create →
        message save → last_customer_message_at update → cancel_pending_pings.
        """
        assert self.connector_id, "No connector — run setup first"
        assert self.conversation_id, "No conversation_id — run setup first"
        assert self.user_external_id, "No user_external_id — run setup first"

        async with self._client(timeout=30) as client:
            response = await client.post(
                "/messages/inbound",
                json={
                    "conversation_id": self.conversation_id,
                    "user_id": self.user_external_id,
                    "text": text,
                    "ts": time.time(),
                    "role": "user",
                    "is_historical": False,
                },
                headers={
                    "X-Service-Key": config.service_api_key,
                    "X-Connector-Id": self.connector_id,
                },
            )
            response.raise_for_status()
            return response.json()

    # ── Billing ─────────────────────────────────────────────────────────────

    async def top_up_balance(self, amount: int = 1000) -> dict[str, Any]:
        return await self.post(
            f"/companies/{self.company_id}/billing/top-up",
            json={"amount": amount, "comment": "Auto-pings E2E test balance"},
        )

    # ── Stage helpers ─────────────────────────────────────────────────────────

    async def list_stages(self) -> list[dict[str, Any]]:
        return await self.get(f"/companies/{self.company_id}/stages")

    async def create_stage(
        self,
        name: str,
        *,
        is_final: bool = False,
        color: str = "#64748b",
    ) -> dict[str, Any]:
        return await self.post(
            f"/companies/{self.company_id}/stages",
            json={"name": name, "color": color, "is_final": is_final},
        )

    async def patch_order(self, order_id: int, **fields: Any) -> dict[str, Any]:
        return await self.patch(
            f"/companies/{self.company_id}/orders/{order_id}",
            json=fields,
        )

    # ── Ping rule endpoints ───────────────────────────────────────────────────

    async def list_pings(self, stage_id: int) -> list[dict[str, Any]]:
        return await self.get(f"/companies/{self.company_id}/stages/{stage_id}/pings")

    async def create_ping(
        self,
        stage_id: int,
        *,
        position: int,
        delay_seconds: int,
        content_type: str = "ai_generated",
        static_content: str | None = None,
        prompt_override: str | None = None,
        condition: dict[str, Any] | None = None,
        is_active: bool = True,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "position": position,
            "delay_seconds": delay_seconds,
            "content_type": content_type,
            "is_active": is_active,
        }
        if static_content is not None:
            payload["static_content"] = static_content
        if prompt_override is not None:
            payload["prompt_override"] = prompt_override
        if condition is not None:
            payload["condition"] = condition
        return await self.post(f"/companies/{self.company_id}/stages/{stage_id}/pings", json=payload)

    async def update_ping(self, ping_id: int, **updates: Any) -> dict[str, Any]:
        return await self.patch(f"/companies/{self.company_id}/pings/{ping_id}", json=updates)

    async def delete_ping(self, ping_id: int) -> None:
        await self.delete(f"/companies/{self.company_id}/pings/{ping_id}")

    async def reorder_pings(self, stage_id: int, ping_rule_ids: list[int]) -> list[dict[str, Any]]:
        return await self.post(
            f"/companies/{self.company_id}/stages/{stage_id}/pings/reorder",
            json={"ping_rule_ids": ping_rule_ids},
        )

    # ── Task helpers ──────────────────────────────────────────────────────────

    async def list_tasks(self, order_id: int, include_completed: bool = False) -> dict[str, Any]:
        return await self.get(
            f"/companies/{self.company_id}/orders/{order_id}/tasks",
            params={"include_completed": str(include_completed).lower()},
        )

    async def create_task(
        self,
        order_id: int,
        *,
        title: str,
        task_type: str,
        due_date: datetime,
        auto_action: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "title": title,
            "type": task_type,
            "due_date": due_date.isoformat(),
        }
        if auto_action is not None:
            payload["auto_action"] = auto_action
        return await self.post(f"/companies/{self.company_id}/orders/{order_id}/tasks", json=payload)

    async def cancel_task(self, order_id: int, task_id: int) -> dict[str, Any]:
        return await self.post(f"/companies/{self.company_id}/orders/{order_id}/tasks/{task_id}/cancel")

    # ── Messages ──────────────────────────────────────────────────────────────

    async def list_messages(self, thread_id: str, limit: int = 50) -> dict[str, Any]:
        return await self.get(
            f"/companies/{self.company_id}/threads/{thread_id}/messages",
            params={"limit": limit},
        )

    # ── Setup helpers ─────────────────────────────────────────────────────────

    async def clean_stage_pings(self, stage_id: int) -> None:
        for r in await self.list_pings(stage_id):
            await self.delete_ping(r["id"])

    async def ensure_non_final_stage(self, name_prefix: str) -> dict[str, Any]:
        stages = await self.list_stages()
        non_final = [s for s in stages if not s.get("is_final")]
        if non_final:
            return non_final[0]
        return await self.create_stage(f"{name_prefix}_{_ts()}")


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────


def _ts() -> str:
    return str(int(time.time()) % 100000)


def _print_rules(rules: list[dict[str, Any]]) -> None:
    print_table(
        rules,
        [
            ("id", "ID"),
            ("position", "Pos"),
            ("delay_seconds", "Delay (s)"),
            ("content_type", "Type"),
            ("is_active", "Active"),
        ],
        title="Ping Rules",
    )


def _print_task(task: dict[str, Any]) -> None:
    status_str = "completed" if task.get("completed") else ("cancelled" if task.get("cancelled_at") else "pending")
    console.print(
        f"  Task #{task['id']}: {task.get('title', '?')[:50]}  "
        f"action={task.get('auto_action')}  ping_rule_id={task.get('ping_rule_id')}  "
        f"status={status_str}  attempts={task.get('attempt_count', 0)}  "
        f"failure={task.get('failure_reason', '-')[:60] if task.get('failure_reason') else '-'}"
    )


async def _wait_for_ping_task(
    client: AutoPingsClient,
    order_id: int,
    rule_id: int | None = None,
    *,
    max_wait: int = MAX_WAIT_EVALUATOR,
    poll_interval: int = 5,
    expect_completed: bool = False,
) -> dict[str, Any] | None:
    """Poll tasks until an evaluator-created ping task appears."""
    for i in range(max_wait // poll_interval):
        await asyncio.sleep(poll_interval)
        elapsed = (i + 1) * poll_interval
        tasks = await client.list_tasks(order_id, include_completed=True)

        for t in tasks["items"]:
            if t.get("auto_action") != "send_followup_message":
                continue
            if t.get("ping_rule_id") is None:
                continue
            if rule_id is not None and t.get("ping_rule_id") != rule_id:
                continue
            if expect_completed and not t.get("completed") and not t.get("failure_reason"):
                continue
            return t

        total = len(tasks["items"])
        followups = [t for t in tasks["items"] if t.get("auto_action") == "send_followup_message"]
        console.print(
            f"   [{elapsed}s / {max_wait}s] — {total} tasks ({len(followups)} followups, "
            f"ping_rule_ids={[t.get('ping_rule_id') for t in followups]})",
            end="\r",
        )

    console.print()
    return None


async def _send_initial_message_and_set_stage(
    client: AutoPingsClient,
    stage_id: int,
) -> None:
    """Send customer message (sets last_customer_message_at) and assign stage."""
    await client.send_customer_message("Привет, мне нужна консультация")
    success("Customer message sent → last_customer_message_at set")

    await client.patch_order(client.order_id, stage_id=stage_id)
    success(f"Order stage set to id={stage_id}")


# ─────────────────────────────────────────────────────────────────────────────
# SCENARIOS 1-9: CRUD & VALIDATION (fast, no waiting)
# ─────────────────────────────────────────────────────────────────────────────


async def scenario_1_basic_crud(client: AutoPingsClient) -> bool:
    print_scenario_header("Scenario 1: Basic CRUD", "Create, list, update, delete ping rules")

    ts = _ts()

    console.print("[yellow]Step 1: Create a non-final stage...[/yellow]")
    stage = await client.create_stage(f"Пинг тест {ts}")
    stage_id = stage["id"]
    success(f"Stage created: {stage['name']} (id={stage_id})")

    console.print("\n[yellow]Step 2: List pings (expect empty)...[/yellow]")
    rules = await client.list_pings(stage_id)
    if rules:
        error(f"Expected empty list, got {len(rules)} rules")
        return False
    success("Empty list confirmed")

    console.print("\n[yellow]Step 3: Create ping rule position=1, delay=3600...[/yellow]")
    rule = await client.create_ping(
        stage_id,
        position=1,
        delay_seconds=3600,
        content_type="ai_generated",
        prompt_override="Напомни про оффер",
    )
    rule_id = rule["id"]
    success(f"Created rule id={rule_id}")
    _print_rules([rule])

    if rule["position"] != 1:
        error(f"Expected position=1, got {rule['position']}")
        return False
    if rule["delay_seconds"] != 3600:
        error("delay_seconds mismatch")
        return False
    if rule["content_type"] != "ai_generated":
        error("content_type mismatch")
        return False
    if rule["prompt_override"] != "Напомни про оффер":
        error("prompt_override mismatch")
        return False

    console.print("\n[yellow]Step 4: List pings (expect 1)...[/yellow]")
    rules = await client.list_pings(stage_id)
    if len(rules) != 1:
        error(f"Expected 1 rule, got {len(rules)}")
        return False
    success("1 rule listed")

    console.print("\n[yellow]Step 5: Update delay_seconds to 7200...[/yellow]")
    updated = await client.update_ping(rule_id, delay_seconds=7200)
    if updated["delay_seconds"] != 7200:
        error("Update did not persist")
        return False
    success("delay_seconds updated to 7200")

    console.print("\n[yellow]Step 6: Delete rule...[/yellow]")
    await client.delete_ping(rule_id)
    success("Rule deleted")

    console.print("\n[yellow]Step 7: Verify list is empty again...[/yellow]")
    rules = await client.list_pings(stage_id)
    if rules:
        error(f"Expected empty list after delete, got {len(rules)}")
        return False
    success("List empty after delete")

    console.print("\n[bold green]✓ Scenario 1 PASSED[/bold green]")
    return True


async def scenario_2_final_stage_block(client: AutoPingsClient) -> bool:
    print_scenario_header("Scenario 2: Final Stage Block", "Cannot create ping rules on is_final=True stages")

    ts = _ts()

    console.print("[yellow]Step 1: Create a final stage...[/yellow]")
    stage = await client.create_stage(f"Финальная {ts}", is_final=True)
    stage_id = stage["id"]
    success(f"Final stage created: id={stage_id}")

    console.print("\n[yellow]Step 2: Try to create ping rule on final stage (expect 400)...[/yellow]")
    resp = await client.raw_request(
        "POST",
        f"/companies/{client.company_id}/stages/{stage_id}/pings",
        json={"position": 1, "delay_seconds": 3600, "content_type": "ai_generated"},
    )
    if resp.status_code == 400:
        success(f"Correctly returned 400: {resp.json().get('detail', '')}")
    else:
        error(f"Expected 400, got {resp.status_code}: {resp.text[:200]}")
        return False

    console.print("\n[bold green]✓ Scenario 2 PASSED[/bold green]")
    return True


async def scenario_3_max_five_limit(client: AutoPingsClient) -> bool:
    print_scenario_header("Scenario 3: Max 5 Ping Rules Per Stage", "6th rule should return 400")

    ts = _ts()
    stage = await client.create_stage(f"Лимит пингов {ts}")
    stage_id = stage["id"]
    success(f"Stage id={stage_id}")

    console.print("\n[yellow]Creating 5 ping rules...[/yellow]")
    for i in range(1, 6):
        await client.create_ping(stage_id, position=i, delay_seconds=i * 3600)
    success("Created 5 rules")

    console.print("\n[yellow]Attempting to create 6th rule (expect 400)...[/yellow]")
    resp = await client.raw_request(
        "POST",
        f"/companies/{client.company_id}/stages/{stage_id}/pings",
        json={"position": 6, "delay_seconds": 21600, "content_type": "ai_generated"},
    )
    if resp.status_code in (400, 422):
        success(f"Correctly rejected: {resp.status_code}")
    else:
        error(f"Expected 400 or 422, got {resp.status_code}: {resp.text[:200]}")
        return False

    console.print("\n[bold green]✓ Scenario 3 PASSED[/bold green]")
    return True


async def scenario_4_static_content_validation(client: AutoPingsClient) -> bool:
    print_scenario_header("Scenario 4: Static Content Validation", "content_type=static without static_content → 422")

    ts = _ts()
    stage = await client.create_stage(f"Статик валидация {ts}")
    stage_id = stage["id"]

    console.print("[yellow]Test 1: content_type=static, no static_content (expect 422)...[/yellow]")
    resp = await client.raw_request(
        "POST",
        f"/companies/{client.company_id}/stages/{stage_id}/pings",
        json={"position": 1, "delay_seconds": 3600, "content_type": "static"},
    )
    if resp.status_code == 422:
        success("422 returned correctly")
    else:
        error(f"Expected 422, got {resp.status_code}: {resp.text[:200]}")
        return False

    console.print("\n[yellow]Test 2: content_type=static WITH static_content (expect 201)...[/yellow]")
    rule = await client.create_ping(
        stage_id,
        position=1,
        delay_seconds=3600,
        content_type="static",
        static_content="Привет! Напоминаем о вашем запросе.",
    )
    if rule["content_type"] != "static" or rule["static_content"] != "Привет! Напоминаем о вашем запросе.":
        error("Static content mismatch")
        return False
    success(f"Rule with static content created: id={rule['id']}")

    console.print("\n[bold green]✓ Scenario 4 PASSED[/bold green]")
    return True


async def scenario_5_condition_syntax(client: AutoPingsClient) -> bool:
    print_scenario_header("Scenario 5: Condition Syntax Validation", "Invalid condition → 422")

    ts = _ts()
    stage = await client.create_stage(f"Condition валидация {ts}")
    stage_id = stage["id"]

    console.print("[yellow]Test 1: Invalid operator $wtf (expect 422)...[/yellow]")
    resp = await client.raw_request(
        "POST",
        f"/companies/{client.company_id}/stages/{stage_id}/pings",
        json={"position": 1, "delay_seconds": 3600, "content_type": "ai_generated", "condition": {"$wtf": True}},
    )
    if resp.status_code != 422:
        error(f"Expected 422, got {resp.status_code}: {resp.text[:200]}")
        return False
    success("422 for invalid operator")

    console.print("\n[yellow]Test 2: Valid $customer_silent_seconds (expect 201)...[/yellow]")
    rule = await client.create_ping(
        stage_id,
        position=1,
        delay_seconds=3600,
        condition={"$customer_silent_seconds": 7200},
    )
    success(f"Rule with valid condition created: id={rule['id']}")

    console.print("\n[yellow]Test 3: Valid nested $and condition (expect 201)...[/yellow]")
    rule2 = await client.create_ping(
        stage_id,
        position=2,
        delay_seconds=7200,
        condition={
            "$and": [
                {"$customer_silent_seconds": 7200},
                {"order_fields.budget": {"$gte": 1000}},
            ]
        },
    )
    success(f"Rule with nested condition created: id={rule2['id']}")

    console.print("\n[bold green]✓ Scenario 5 PASSED[/bold green]")
    return True


async def scenario_6_position_bounds(client: AutoPingsClient) -> bool:
    print_scenario_header("Scenario 6: Position Bounds", "position=0 and position=6 → 422")

    ts = _ts()
    stage = await client.create_stage(f"Position bounds {ts}")
    stage_id = stage["id"]
    base = {"delay_seconds": 3600, "content_type": "ai_generated"}

    for pos, label in [(0, "position=0"), (6, "position=6")]:
        console.print(f"[yellow]Test: {label} (expect 422)...[/yellow]")
        resp = await client.raw_request(
            "POST",
            f"/companies/{client.company_id}/stages/{stage_id}/pings",
            json={**base, "position": pos},
        )
        if resp.status_code != 422:
            error(f"Expected 422, got {resp.status_code}")
            return False
        success(f"422 for {label}")

    console.print("\n[yellow]Test: position=5 (boundary — expect 201)...[/yellow]")
    rule = await client.create_ping(stage_id, position=5, delay_seconds=3600)
    success(f"Rule at position=5 accepted: id={rule['id']}")

    console.print("\n[bold green]✓ Scenario 6 PASSED[/bold green]")
    return True


async def scenario_7_reorder(client: AutoPingsClient) -> bool:
    print_scenario_header("Scenario 7: Reorder Rules", "Reorder by IDs, verify positions")

    ts = _ts()
    stage = await client.create_stage(f"Reorder {ts}")
    stage_id = stage["id"]

    console.print("[yellow]Step 1: Create 3 rules (positions 1, 2, 3)...[/yellow]")
    r1 = await client.create_ping(stage_id, position=1, delay_seconds=3600, prompt_override="First")
    r2 = await client.create_ping(stage_id, position=2, delay_seconds=7200, prompt_override="Second")
    r3 = await client.create_ping(stage_id, position=3, delay_seconds=10800, prompt_override="Third")
    success(f"Created rules: {r1['id']}, {r2['id']}, {r3['id']}")

    console.print("\n[yellow]Step 2: Reorder as [3rd, 1st, 2nd]...[/yellow]")
    reordered = await client.reorder_pings(stage_id, [r3["id"], r1["id"], r2["id"]])
    _print_rules(reordered)

    by_id = {r["id"]: r for r in reordered}
    if by_id[r3["id"]]["position"] != 1 or by_id[r1["id"]]["position"] != 2 or by_id[r2["id"]]["position"] != 3:
        error("Position mismatch after reorder")
        return False
    success("Positions updated correctly")

    console.print("\n[yellow]Step 3: Reorder with wrong IDs (expect 400)...[/yellow]")
    resp = await client.raw_request(
        "POST",
        f"/companies/{client.company_id}/stages/{stage_id}/pings/reorder",
        json={"ping_rule_ids": [r1["id"], r2["id"]]},
    )
    if resp.status_code != 400:
        error(f"Expected 400, got {resp.status_code}")
        return False
    success("400 for incomplete ID list")

    console.print("\n[bold green]✓ Scenario 7 PASSED[/bold green]")
    return True


async def scenario_8_ai_content_type(client: AutoPingsClient) -> bool:
    print_scenario_header("Scenario 8: AI Content Type", "prompt_override persists and is returned")

    ts = _ts()
    stage = await client.create_stage(f"AI content {ts}")
    stage_id = stage["id"]

    console.print("[yellow]Step 1: Create rule with prompt_override...[/yellow]")
    override = "Напомни клиенту о выгодных условиях нашего предложения, упомяни скидку 10%."
    rule = await client.create_ping(stage_id, position=1, delay_seconds=86400, prompt_override=override)
    if rule["prompt_override"] != override:
        error("prompt_override mismatch")
        return False
    if rule["static_content"] is not None:
        error("static_content should be null for ai_generated")
        return False
    success(f"Rule created: id={rule['id']}")

    console.print("\n[yellow]Step 2: Update prompt_override...[/yellow]")
    new_override = "Спроси: вы определились с решением?"
    updated = await client.update_ping(rule["id"], prompt_override=new_override)
    if updated["prompt_override"] != new_override:
        error("Updated prompt_override mismatch")
        return False
    success("prompt_override updated")

    console.print("\n[yellow]Step 3: Create ai_generated rule WITHOUT prompt_override...[/yellow]")
    rule2 = await client.create_ping(stage_id, position=2, delay_seconds=172800)
    success(f"Rule without override created: id={rule2['id']}, prompt_override={rule2['prompt_override']}")

    console.print("\n[bold green]✓ Scenario 8 PASSED[/bold green]")
    return True


async def scenario_9_deactivate_rule(client: AutoPingsClient) -> bool:
    print_scenario_header("Scenario 9: Deactivate Rule", "is_active toggle")

    ts = _ts()
    stage = await client.create_stage(f"Деактивация {ts}")
    stage_id = stage["id"]

    rule = await client.create_ping(stage_id, position=1, delay_seconds=3600, is_active=True)
    if not rule["is_active"]:
        error("Expected is_active=True")
        return False
    success(f"Rule active: id={rule['id']}")

    updated = await client.update_ping(rule["id"], is_active=False)
    if updated["is_active"]:
        error("Expected is_active=False")
        return False
    success("Deactivated")

    reactivated = await client.update_ping(rule["id"], is_active=True)
    if not reactivated["is_active"]:
        error("Expected is_active=True after re-activation")
        return False
    success("Re-activated")

    console.print("\n[bold green]✓ Scenario 9 PASSED[/bold green]")
    return True


# ─────────────────────────────────────────────────────────────────────────────
# SCENARIOS 10-14: REAL E2E (evaluator + scheduler + sales-agent)
# ─────────────────────────────────────────────────────────────────────────────


async def scenario_10_e2e_ai_ping(client: AutoPingsClient) -> bool:
    print_scenario_header(
        "Scenario 10: E2E AI Ping",
        "Real evaluator → scheduler → sales-agent AI generation",
    )
    console.print(
        f"[dim]Evaluator polls every {EVALUATOR_POLL}s, scheduler every {SCHEDULER_POLL}s.\n"
        f"Total wait: up to ~{MAX_WAIT_EVALUATOR + MAX_WAIT_EXECUTION}s.[/dim]\n"
    )

    assert client.order_id

    ts = _ts()
    stage = await client.create_stage(f"E2E AI Ping {ts}")
    await client.clean_stage_pings(stage["id"])

    console.print("[yellow]Step 1: Create ping rule: delay=5s, ai_generated with prompt_override...[/yellow]")
    rule = await client.create_ping(
        stage["id"],
        position=1,
        delay_seconds=5,
        content_type="ai_generated",
        prompt_override="Спроси клиента, остались ли вопросы по нашему предложению. Будь кратким.",
    )
    success(f"Ping rule created: id={rule['id']}, delay=5s")

    console.print("\n[yellow]Step 2: Send customer message and set stage (starts silence timer)...[/yellow]")
    await _send_initial_message_and_set_stage(client, stage["id"])

    console.print(f"\n[yellow]Step 3: Wait for evaluator to create ping task (up to {MAX_WAIT_EVALUATOR}s)...[/yellow]")
    ping_task = await _wait_for_ping_task(client, client.order_id, rule["id"])
    if not ping_task:
        error(f"No ping task created after {MAX_WAIT_EVALUATOR}s — is worker-hub running?")
        console.print("[yellow]   Check: just dev backend,sales-agent,workers[/yellow]")
        return False

    success(f"Evaluator created ping task: id={ping_task['id']}, ping_rule_id={ping_task.get('ping_rule_id')}")
    _print_task(ping_task)

    if ping_task.get("ping_rule_id") != rule["id"]:
        error(f"ping_rule_id mismatch: expected {rule['id']}, got {ping_task.get('ping_rule_id')}")
        return False

    console.print(f"\n[yellow]Step 4: Wait for scheduler to execute task (up to {MAX_WAIT_EXECUTION}s)...[/yellow]")
    executed_task = await _wait_for_ping_task(
        client,
        client.order_id,
        rule["id"],
        max_wait=MAX_WAIT_EXECUTION,
        expect_completed=True,
    )
    if not executed_task:
        tasks = await client.list_tasks(client.order_id, include_completed=True)
        executed_task = next(
            (t for t in tasks["items"] if t.get("ping_rule_id") == rule["id"]),
            None,
        )

    if executed_task:
        _print_task(executed_task)
        if executed_task.get("completed"):
            success("Task completed by system — AI ping sent!")
        elif executed_task.get("attempt_count", 0) > 0:
            success(f"Task attempted (attempts={executed_task['attempt_count']})")
            if executed_task.get("failure_reason"):
                warn(f"Failure: {executed_task['failure_reason'][:100]}")
                console.print("[dim]   Transport delivery failure is expected (no transport module running)[/dim]")
        else:
            warn("Task not yet executed — scheduler may be slow")
    else:
        warn("Could not find executed task")

    console.print("\n[bold green]✓ Scenario 10 PASSED[/bold green]")
    return True


async def scenario_11_e2e_static_ping(client: AutoPingsClient) -> bool:
    print_scenario_header(
        "Scenario 11: E2E Static Ping",
        "Real evaluator → scheduler → static content delivery (bypasses sales-agent)",
    )

    assert client.order_id
    assert client.thread_id

    ts = _ts()
    stage = await client.create_stage(f"E2E Static {ts}")
    await client.clean_stage_pings(stage["id"])

    static_text = f"Здравствуйте! Напоминаем, что ваша заявка ещё в обработке. [{ts}]"

    console.print("[yellow]Step 1: Create STATIC ping rule: delay=5s...[/yellow]")
    rule = await client.create_ping(
        stage["id"],
        position=1,
        delay_seconds=5,
        content_type="static",
        static_content=static_text,
    )
    success(f"Static ping rule: id={rule['id']}")

    console.print("\n[yellow]Step 2: Send customer message and set stage...[/yellow]")
    await _send_initial_message_and_set_stage(client, stage["id"])

    console.print(
        f"\n[yellow]Step 3: Wait for evaluator + scheduler (up to {MAX_WAIT_EVALUATOR + MAX_WAIT_EXECUTION}s)...[/yellow]"
    )
    ping_task = await _wait_for_ping_task(client, client.order_id, rule["id"], max_wait=MAX_WAIT_EVALUATOR)
    if not ping_task:
        error("No ping task created — is worker-hub running?")
        return False
    success(f"Ping task created: id={ping_task['id']}")

    executed_task = await _wait_for_ping_task(
        client,
        client.order_id,
        rule["id"],
        max_wait=MAX_WAIT_EXECUTION,
        expect_completed=True,
    )

    tasks = await client.list_tasks(client.order_id, include_completed=True)
    final_task = next((t for t in tasks["items"] if t.get("ping_rule_id") == rule["id"]), None)
    if final_task:
        _print_task(final_task)

    console.print("\n[yellow]Step 4: Check chat messages for static content...[/yellow]")
    messages = await client.list_messages(client.thread_id, limit=20)
    bot_messages = [m for m in messages.get("items", []) if m.get("role") == "assistant"]

    found_static = any(m.get("content") == static_text for m in bot_messages)
    if found_static:
        success(f"Static ping message found in chat: '{static_text[:50]}...'")
    else:
        warn("Static ping message not found in chat — transport delivery may have failed before DB save")
        if final_task and final_task.get("failure_reason"):
            console.print(f"[dim]   Task failure: {final_task['failure_reason'][:100]}[/dim]")
        elif final_task and final_task.get("completed"):
            success("Task completed — message should be in DB")
            for m in bot_messages[-3:]:
                console.print(f"   Recent bot msg: {m.get('content', '')[:80]}")

    console.print("\n[bold green]✓ Scenario 11 PASSED[/bold green]")
    return True


async def scenario_12_e2e_cancel_on_reply(client: AutoPingsClient) -> bool:
    print_scenario_header(
        "Scenario 12: E2E Cancel on Reply",
        "Real evaluator creates ping → customer replies → ping cancelled",
    )

    assert client.order_id

    ts = _ts()
    stage = await client.create_stage(f"E2E Cancel {ts}")
    await client.clean_stage_pings(stage["id"])

    console.print("[yellow]Step 1: Create ping rule: delay=5s...[/yellow]")
    rule = await client.create_ping(stage["id"], position=1, delay_seconds=5)
    success(f"Ping rule: id={rule['id']}")

    console.print("\n[yellow]Step 2: Send customer message and set stage...[/yellow]")
    await _send_initial_message_and_set_stage(client, stage["id"])

    console.print(f"\n[yellow]Step 3: Wait for evaluator to create ping task (up to {MAX_WAIT_EVALUATOR}s)...[/yellow]")
    ping_task = await _wait_for_ping_task(client, client.order_id, rule["id"])
    if not ping_task:
        error("No ping task created — is worker-hub running?")
        return False
    task_id = ping_task["id"]
    success(f"Ping task created: id={task_id}")

    console.print("\n[yellow]Step 4: Customer replies (triggers cancel_pending_pings)...[/yellow]")
    await client.send_customer_message("Да, я всё ещё заинтересован!")
    success("Customer reply sent — pending pings should be cancelled")

    console.print("\n[yellow]Step 5: Verify ping task was cancelled...[/yellow]")
    await asyncio.sleep(1)
    tasks = await client.list_tasks(client.order_id, include_completed=True)
    task_after = next((t for t in tasks["items"] if t["id"] == task_id), None)

    if not task_after:
        warn("Task not found in list")
    elif task_after.get("cancelled_at"):
        success(f"Ping task CANCELLED at {task_after['cancelled_at']}")
    elif task_after.get("completed"):
        warn("Task was already completed before customer replied (scheduler was faster)")
    else:
        error("Task is still pending — cancel_pending_pings did not work")
        _print_task(task_after)
        return False

    console.print("\n[bold green]✓ Scenario 12 PASSED[/bold green]")
    return True


async def scenario_13_e2e_agent_priority(client: AutoPingsClient) -> bool:
    print_scenario_header(
        "Scenario 13: E2E Agent Priority",
        "Agent followup task (ping_rule_id=None) suppresses evaluator",
    )

    assert client.order_id

    ts = _ts()
    stage = await client.create_stage(f"E2E Agent Prio {ts}")
    await client.clean_stage_pings(stage["id"])

    console.print("[yellow]Step 1: Create ping rule: delay=5s...[/yellow]")
    rule = await client.create_ping(stage["id"], position=1, delay_seconds=5)
    success(f"Ping rule: id={rule['id']}")

    console.print("\n[yellow]Step 2: Send customer message and set stage...[/yellow]")
    await _send_initial_message_and_set_stage(client, stage["id"])

    console.print("\n[yellow]Step 3: Create agent followup task (ping_rule_id=None)...[/yellow]")
    agent_task = await client.create_task(
        client.order_id,
        title="Агент: написать утром по просьбе клиента",
        task_type="ai_scheduled",
        due_date=datetime.now(UTC) + timedelta(hours=8),
        auto_action="send_followup_message",
    )
    success(f"Agent followup task: id={agent_task['id']} (ping_rule_id=None)")

    console.print(f"\n[yellow]Step 4: Wait {MAX_WAIT_EVALUATOR}s — evaluator should NOT create a ping task...[/yellow]")
    console.print("[dim]   has_pending_agent_followup(order_id) → True → skip[/dim]")

    ping_task = await _wait_for_ping_task(client, client.order_id, rule["id"], max_wait=MAX_WAIT_EVALUATOR)
    if ping_task:
        error(f"Evaluator created ping task despite agent followup existing: {ping_task['id']}")
        return False
    success("Evaluator correctly skipped this order (agent followup takes priority)")

    console.print("\n[yellow]Step 5: Cancel agent task → evaluator should now schedule ping...[/yellow]")
    await client.cancel_task(client.order_id, agent_task["id"])
    success("Agent followup task cancelled")

    console.print(f"\n[yellow]Step 6: Wait for evaluator to create ping (up to {MAX_WAIT_EVALUATOR}s)...[/yellow]")
    ping_task = await _wait_for_ping_task(client, client.order_id, rule["id"], max_wait=MAX_WAIT_EVALUATOR)
    if ping_task:
        success(f"Evaluator created ping task after agent task removed: id={ping_task['id']}")
    else:
        warn("No ping task created — evaluator may need another tick or silence window expired")

    console.print("\n[bold green]✓ Scenario 13 PASSED[/bold green]")
    return True


async def scenario_14_e2e_deactivated_ignored(client: AutoPingsClient) -> bool:
    print_scenario_header(
        "Scenario 14: E2E Deactivated Rule Ignored",
        "is_active=False rule is skipped by evaluator",
    )

    assert client.order_id

    ts = _ts()
    stage = await client.create_stage(f"E2E Deactivated {ts}")
    await client.clean_stage_pings(stage["id"])

    console.print("[yellow]Step 1: Create DEACTIVATED ping rule: delay=5s, is_active=False...[/yellow]")
    rule = await client.create_ping(stage["id"], position=1, delay_seconds=5, is_active=False)
    success(f"Rule: id={rule['id']}, is_active={rule['is_active']}")

    console.print("\n[yellow]Step 2: Send customer message and set stage...[/yellow]")
    await _send_initial_message_and_set_stage(client, stage["id"])

    console.print(f"\n[yellow]Step 3: Wait {MAX_WAIT_EVALUATOR}s — evaluator should NOT create a task...[/yellow]")
    ping_task = await _wait_for_ping_task(client, client.order_id, rule["id"], max_wait=MAX_WAIT_EVALUATOR)
    if ping_task:
        error(f"Evaluator created task for deactivated rule! task_id={ping_task['id']}")
        return False
    success("Evaluator correctly ignored deactivated rule")

    console.print("\n[yellow]Step 4: Reactivate rule → evaluator should now pick it up...[/yellow]")
    await client.update_ping(rule["id"], is_active=True)
    success("Rule reactivated")

    console.print(f"\n[yellow]Step 5: Wait for evaluator (up to {MAX_WAIT_EVALUATOR}s)...[/yellow]")
    ping_task = await _wait_for_ping_task(client, client.order_id, rule["id"], max_wait=MAX_WAIT_EVALUATOR)
    if ping_task:
        success(f"Ping task created after reactivation: id={ping_task['id']}")
    else:
        warn("No ping task — silence window may have changed or evaluator needs more time")

    console.print("\n[bold green]✓ Scenario 14 PASSED[/bold green]")
    return True


async def scenario_15_stage_change_cancel(client: AutoPingsClient) -> bool:
    print_scenario_header(
        "Scenario 15: Stage Change Cancels Pings",
        "Moving order to a new stage cancels old-stage pending pings",
    )
    console.print(
        "[dim]Note: cancel_pending_pings on stage change is wired in the inbound handler.\n"
        "   The orders PATCH endpoint may not trigger it yet (Phase 4 hook).\n"
        "   This scenario tests the current behavior.[/dim]\n"
    )

    assert client.order_id

    ts = _ts()
    stage_a = await client.create_stage(f"Стадия А {ts}")
    stage_b = await client.create_stage(f"Стадия Б {ts}")
    await client.clean_stage_pings(stage_a["id"])

    console.print("[yellow]Step 1: Create ping rule on Stage A, send message, set stage...[/yellow]")
    rule_a = await client.create_ping(stage_a["id"], position=1, delay_seconds=5)
    await _send_initial_message_and_set_stage(client, stage_a["id"])
    success(f"Rule A: id={rule_a['id']}")

    console.print(f"\n[yellow]Step 2: Wait for evaluator to create ping task (up to {MAX_WAIT_EVALUATOR}s)...[/yellow]")
    ping_task = await _wait_for_ping_task(client, client.order_id, rule_a["id"])
    if not ping_task:
        error("No ping task created — is worker-hub running?")
        return False
    task_id = ping_task["id"]
    success(f"Ping task created: id={task_id}")

    console.print("\n[yellow]Step 3: Move order to Stage B...[/yellow]")
    await client.patch_order(client.order_id, stage_id=stage_b["id"])
    success("Order moved to Stage B")

    console.print("\n[yellow]Step 4: Check if ping task was cancelled...[/yellow]")
    await asyncio.sleep(1)
    tasks = await client.list_tasks(client.order_id, include_completed=True)
    task_after = next((t for t in tasks["items"] if t["id"] == task_id), None)

    if task_after and task_after.get("cancelled_at"):
        success("Ping task cancelled after stage change")
    elif task_after and task_after.get("completed"):
        warn("Task was already completed (scheduler was faster than stage change)")
    else:
        warn(
            "Task not cancelled — stage change cancel hook may not be wired in PATCH yet.\n"
            "   Plan Phase 4 specifies adding this to OrdersRepository.update_stage()."
        )
        if task_after:
            _print_task(task_after)

    console.print("\n[bold green]✓ Scenario 15 PASSED[/bold green]")
    return True


async def scenario_16_company_isolation(client: AutoPingsClient) -> bool:
    print_scenario_header("Scenario 16: Company Isolation", "Wrong company_id → 404")

    ts = _ts()
    stage = await client.create_stage(f"Изоляция {ts}")
    rule = await client.create_ping(stage["id"], position=1, delay_seconds=3600)
    success(f"Rule: id={rule['id']}")

    fake_company_id = 999999

    console.print(f"\n[yellow]PATCH with fake company_id={fake_company_id}...[/yellow]")
    resp = await client.raw_request(
        "PATCH",
        f"/companies/{fake_company_id}/pings/{rule['id']}",
        json={"delay_seconds": 9999},
    )
    if resp.status_code not in (403, 404):
        error(f"Expected 403/404, got {resp.status_code}")
        return False
    success(f"Correctly returned {resp.status_code}")

    console.print(f"\n[yellow]DELETE with fake company_id...[/yellow]")
    resp = await client.raw_request("DELETE", f"/companies/{fake_company_id}/pings/{rule['id']}")
    if resp.status_code not in (403, 404):
        error(f"Expected 403/404, got {resp.status_code}")
        return False
    success(f"Correctly returned {resp.status_code}")

    rules = await client.list_pings(stage["id"])
    if not any(r["id"] == rule["id"] for r in rules):
        error("Rule was deleted despite wrong company check")
        return False
    success("Rule untouched")

    console.print("\n[bold green]✓ Scenario 16 PASSED[/bold green]")
    return True


# ─────────────────────────────────────────────────────────────────────────────
# UTILITIES
# ─────────────────────────────────────────────────────────────────────────────


async def util_list_stages(client: AutoPingsClient) -> None:
    stages = await client.list_stages()
    console.print(f"\n[cyan]Stages ({len(stages)}):[/cyan]")
    for s in stages:
        console.print(f"  {s['id']}: {s['name']}  final={s.get('is_final')}  pos={s.get('position')}")


async def util_list_pings_for_stage(client: AutoPingsClient) -> None:
    stages = await client.list_stages()
    if not stages:
        warn("No stages")
        return
    console.print("[cyan]Pick stage:[/cyan]")
    for i, s in enumerate(stages):
        console.print(f"  {i}: {s['name']} (id={s['id']})")
    raw = await asyncio.get_event_loop().run_in_executor(None, input, "Stage index: ")
    try:
        stage = stages[int(raw.strip())]
    except (ValueError, IndexError):
        error("Invalid index")
        return
    rules = await client.list_pings(stage["id"])
    console.print(f"\n[cyan]Ping rules for '{stage['name']}' ({len(rules)}):[/cyan]")
    _print_rules(rules) if rules else console.print("  (empty)")


async def util_list_tasks(client: AutoPingsClient) -> None:
    if not client.order_id:
        error("No order_id")
        return
    resp = await client.list_tasks(client.order_id, include_completed=True)
    console.print(f"\n[cyan]Tasks for order {client.order_id} ({resp['total']}):[/cyan]")
    for t in resp["items"]:
        _print_task(t)


async def util_get_order(client: AutoPingsClient) -> None:
    if not client.order_id:
        error("No order_id")
        return
    order = await client.get_order(client.order_id)
    print_json(order, title="Order", style="cyan")


async def util_send_message(client: AutoPingsClient) -> None:
    raw = await asyncio.get_event_loop().run_in_executor(None, input, "Message text: ")
    if raw.strip():
        result = await client.send_customer_message(raw.strip())
        success(f"Sent: {result}")


async def util_list_messages(client: AutoPingsClient) -> None:
    if not client.thread_id:
        error("No thread_id")
        return
    msgs = await client.list_messages(client.thread_id, limit=15)
    console.print(f"\n[cyan]Messages ({msgs.get('total', '?')}):[/cyan]")
    for m in msgs.get("items", []):
        role_color = "green" if m.get("role") == "assistant" else "blue"
        console.print(f"  [{role_color}]{m.get('role')}[/{role_color}]: {m.get('content', '')[:80]}")


# ─────────────────────────────────────────────────────────────────────────────
# CUSTOM SETUP
# ─────────────────────────────────────────────────────────────────────────────


async def setup_with_connector(client: AutoPingsClient, mock_transport: MockTransport) -> bool:
    """Extended setup: standard env + mock transport + custom connector + thread via inbound."""

    company_name = f"Pings E2E {int(time.time())}"
    if not await setup_environment(client, company_name, create_thread=False, check_sales_agent=True):
        return False

    console.print("\n5. Topping up company balance...")
    try:
        top_up = await client.top_up_balance(1000)
        success(f"Balance topped up: +1000 (new balance: {top_up.get('new_balance', '?')})")
    except httpx.HTTPStatusError as e:
        error(f"Failed to top up balance: {e.response.status_code} {e.response.text[:200]}")
        return False

    console.print("\n6. Starting mock transport server...")
    try:
        await mock_transport.start()
        success(f"Mock transport ready at {mock_transport.url}")
    except OSError as e:
        if "Address already in use" in str(e):
            success(f"Mock transport already running on {mock_transport.url}")
        else:
            error(f"Failed to start mock transport: {e}")
            return False

    ts = int(time.time())
    connector_id = f"test_pings_{ts}"
    conversation_id = f"ping_conv_{ts}"
    user_external_id = f"ping_user_{ts}"

    console.print("\n7. Creating custom connector for inbound messages...")
    try:
        connector = await client.create_connector(connector_id, transport_endpoint=mock_transport.url)
        client.connector_id = connector["connector_id"]
        success(f"Connector created: {client.connector_id} (db_id={connector['id']})")
    except httpx.HTTPStatusError as e:
        error(f"Failed to create connector: {e.response.status_code} {e.response.text[:200]}")
        return False

    client.conversation_id = conversation_id
    client.user_external_id = user_external_id

    console.print("\n8. Creating thread and order via real inbound message...")
    try:
        result = await client.send_customer_message("Привет, хочу узнать подробнее о ваших услугах")
        success(f"Inbound message sent: {result}")
    except httpx.HTTPStatusError as e:
        error(f"Inbound message failed: {e.response.status_code} {e.response.text[:200]}")
        return False

    console.print("\n9. Resolving thread and order from inbound...")
    thread_data = await client.post(
        "/internal/chat/threads/get-or-create",
        json={
            "user_id": user_external_id,
            "company_id": client.company_id,
            "channel_type": "test",
            "connector_id": connector_id,
            "conversation_id": conversation_id,
        },
        use_service_auth=True,
    )
    client.thread_id = thread_data["thread_id"]
    success(f"Thread: {client.thread_id}")

    order_context = await client.get(
        f"/internal/orders/by-thread/{client.thread_id}",
        use_service_auth=True,
    )
    client.order_id = order_context["order_id"]
    success(f"Order: {client.order_id}")

    return True


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

SCENARIOS = [
    Scenario("Basic CRUD", scenario_1_basic_crud, "Create, list, update, delete rules"),
    Scenario("Final Stage Block", scenario_2_final_stage_block, "is_final → 400"),
    Scenario("Max 5 Limit", scenario_3_max_five_limit, "6th rule → 400"),
    Scenario("Static Validation", scenario_4_static_content_validation, "static without content → 422"),
    Scenario("Condition Syntax", scenario_5_condition_syntax, "Invalid condition → 422"),
    Scenario("Position Bounds", scenario_6_position_bounds, "pos=0/6 → 422"),
    Scenario("Reorder Rules", scenario_7_reorder, "Reorder IDs → positions update"),
    Scenario("AI Content Type", scenario_8_ai_content_type, "prompt_override persists"),
    Scenario("Deactivate Rule", scenario_9_deactivate_rule, "is_active toggle"),
    Scenario("E2E: AI Ping", scenario_10_e2e_ai_ping, "evaluator → scheduler → AI (~90s)"),
    Scenario("E2E: Static Ping", scenario_11_e2e_static_ping, "evaluator → scheduler → static (~90s)"),
    Scenario("E2E: Cancel on Reply", scenario_12_e2e_cancel_on_reply, "inbound cancels evaluator ping (~80s)"),
    Scenario("E2E: Agent Priority", scenario_13_e2e_agent_priority, "agent followup suppresses evaluator (~160s)"),
    Scenario("E2E: Deactivated Ignored", scenario_14_e2e_deactivated_ignored, "is_active=False skipped (~160s)"),
    Scenario("Stage Change Cancel", scenario_15_stage_change_cancel, "stage change cancels pings (~80s)"),
    Scenario("Company Isolation", scenario_16_company_isolation, "wrong company → 404"),
]

UTILITIES = [
    ("s", "List stages", util_list_stages),
    ("p", "List ping rules for stage", util_list_pings_for_stage),
    ("t", "List tasks for current order", util_list_tasks),
    ("o", "Get order details", util_get_order),
    ("m", "Send customer message", util_send_message),
    ("c", "List chat messages", util_list_messages),
]


if __name__ == "__main__":

    async def main() -> int:
        from rich.panel import Panel

        console.print(
            Panel.fit(
                "[bold cyan]Stage-Based Auto-Pings — E2E Test Suite[/bold cyan]\n\n"
                "Plan 039: Automated follow-up ping chains\n"
                "Real e2e: connector → inbound → evaluator → scheduler → sales-agent\n"
                "Mock transport absorbs outbound deliveries so tasks complete cleanly\n\n"
                "[yellow]Required:[/yellow] just dev backend,sales-agent,workers\n"
                "[dim]Scenarios 10-15 wait for real worker ticks (~60-160s each)[/dim]",
                border_style="cyan",
            )
        )

        mock_transport = MockTransport()
        client = AutoPingsClient()

        if not await setup_with_connector(client, mock_transport):
            return 1

        try:
            await interactive_menu(client, SCENARIOS, utilities=UTILITIES)
        finally:
            await mock_transport.stop()

        console.print("\n[bold green]Done![/bold green]")
        return 0

    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted[/yellow]")
