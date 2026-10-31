---
description: Fix failing tests after a refactor. Only change test code, never production code.
---

# Fix Failing Tests

You are fixing tests that broke after production code was refactored.

## Hard Rules

1. **Default to changing only test code** (`tests/` directories). If production code is genuinely broken or poorly written, **stop and ask the user first** — never silently change `src/` on your own.
2. **Do NOT stop until every test passes.** Run → fix → run → fix until green.
3. **Do NOT ask the user** to run tests or verify — run them yourself.
4. **Do NOT silently weaken assertions** (e.g. replacing `assert x == 202` with `assert x`). If an assertion needs updating, match the new actual behavior and verify it makes sense.
5. **Do NOT create documentation files.**

## Testing Commands

Use `uv run pytest` with a **specific file or test** to iterate fast — don't re-run the entire module when you already know which files are broken.

```bash
# Single file (main iteration tool)
cd apps/backend && uv run pytest tests/domains/messages/test_routers.py -x -q

# Single test
cd apps/backend && uv run pytest tests/domains/messages/test_routers.py::TestInboundMessageRouter::test_inbound_with_bearer_token -x -q

# Full module suite (only for initial discovery and final confirmation)
cd apps/backend && uv run pytest -x -q
cd apps/sales-agent && uv run pytest -x -q
```

**Always use `-x` (stop on first failure) when iterating.**

## Workflow

1. Run the **full module suite once** with `-x -q` to discover all failing files/tests.
2. Read the failing test AND the production code it exercises to understand **what changed**.
3. Fix the test to match the new behavior.
4. Re-run **only that file** (or that single test) to verify — don't waste time re-running passing files.
5. Move to the next failing file. Never re-run already-green files mid-session.
6. After all known failures are fixed, run the full module suite **once without `-x`** as final confirmation.
