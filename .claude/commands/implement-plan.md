Implement the plan tagged above following these rules:

## Execution Order
- Start with schema/contract changes (libs/common) if any
- Execute phases in order specified in the plan
- Create todo list tracking each phase/task
- Verify each change compiles/lints before moving on
- Do not skip steps, do not add unrequested features — propose them after

## Parallel Execution via Sub-Agents (Task tool)

**KISS: Skip this entire section for plans with ≤ 3 phases or single-module scope. Just execute sequentially.**

Before starting, analyze the plan for parallelization opportunities. Plans often have phases that CAN run concurrently.

### When to parallelize phases

Launch parallel sub-agents when ALL conditions are met:
1. **Different files** — phases touch non-overlapping files (e.g., backend models vs. sales-agent tools)
2. **Clear contract boundary** — the dependency between phases is an interface/schema, not implementation details. If Phase B depends on Phase A's output, the contract (types, function signatures, API shape) must be fully defined in the plan.
3. **Different modules** — e.g., `apps/backend/` vs. `apps/sales-agent/` vs. `libs/common/`

### When NOT to parallelize

Run sequentially when:
- Phase B imports or calls code that Phase A creates (and the exact implementation matters)
- Both phases modify the same file
- Phase A is a migration/schema change that Phase B depends on at runtime
- The plan explicitly states sequential order for those phases

### Parallelization pattern

```
1. Identify phase groups:
   - Foundation (must run first): schema changes, shared models, migrations
   - Parallelizable: phases touching different modules with defined contracts
   - Integration (must run last): wiring, router registration, docker-compose

2. Execute foundation phases sequentially

3. Launch parallel sub-agents for independent phases:
   - Each agent gets: full plan context, phase assignment, shared contracts from foundation
   - Each agent prompt must include: what files to create/modify, what interfaces to conform to,
     what NOT to touch (other agents' territory)
   - Set readonly=false for implementation agents

4. After parallel agents complete: run integration/wiring phase sequentially

5. Final verification: lints, imports, cross-module consistency
```

### Sub-agent prompt template

When delegating a phase to a sub-agent, include:
- The full phase description from the plan
- Shared types/contracts established in foundation phases (copy actual code, not references)
- Explicit file boundaries: "You own these files: [...]. Do NOT modify: [...]"
- Module-specific context: relevant existing code patterns, imports, conventions
- Verification step: "After implementation, run `uv run ruff check --fix` in the module"

### Example: Plan 027 (Tasks & Reminders)

```
Foundation (sequential):
  - Phase 1: Data model, migration, repository (libs/common + backend models)

Parallel group (2 agents):
  - Agent A: Phase 2 + Phase 3 (service layer + REST API — all in apps/backend/)
  - Agent B: Phase 5.1-5.4 (sales-agent integration — all in apps/sales-agent/)
  Both agents receive: Task model definition, shared schemas from Phase 1

Sequential (after parallel):
  - Phase 4: Scheduler worker (needs both backend service and sales-agent client)
  - Phase 6: Tests
  - Wiring: router registration, docker-compose
```

### Safety rules
- Maximum 3 sub-agents in parallel (keep 1 slot for yourself to monitor)
- If a sub-agent's output conflicts with another's, resolve manually — do not re-run blindly
- After all agents complete, do a full consistency pass: check imports, verify cross-references
- If the plan has < 3 phases or all phases touch the same module — skip parallelization, just execute sequentially

## Post-Implementation Polish

After all phases are complete and lints pass, run a **rules compliance check**:

1. Read `.claude/skills/rules-compliance/SKILL.md` and execute its full procedure against all files changed during implementation.
2. Fix any violations before signaling completion to the user.

This step is **not optional** — it catches DI chaining issues, cross-module repo leaks, and FastAPI anti-patterns that linters don't cover.

## General Rules
- Be precise. Verify assumptions against code.
- Prefer safe, minimal changes. Check twice, commit once.
- Ask for clarification if task is ambiguous.