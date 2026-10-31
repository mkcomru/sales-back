From the chat context and current message create new numbered plan in @repo-root/plans that captures the main objective and any critical points that been discussed.

**Required section: "Зачем это делаем"** — Generate a brief explanation of WHY this task matters:
- What problem does it solve for users?
- What value does it bring to the product from UI/UX perspective?
- What becomes possible after implementation?

This section helps developers understand the purpose beyond "just endpoints". Generate it automatically based on task context.

## Phase Structure (skip for plans with ≤ 3 simple steps or single-module changes)

Each phase must:
- **List files** it creates or modifies — explicit ownership prevents ambiguity during implementation
- **State dependencies** — if Phase B depends on Phase A, name exactly what it depends on (types, function signatures, API shape), not just "depends on Phase A"
- **Stay within one module** when practical — if a phase spans `apps/backend/` and `apps/sales-agent/`, split it into two phases unless they share < 2 files

Shared contracts (types, schemas, enums in `libs/common`) should live in an early foundation phase, so consumer phases have a concrete interface to code against.

Group phases by module cohesion, not by architectural layer. Prefer "Phase 3: Backend API + service for tasks" over "Phase 3: all services across all modules".

## Model Recommendation

At the end of the plan, add a section **"Рекомендуемая модель для выполнения"** with a recommendation of which model should execute this plan. Available models:

| Model | Cost | Speed | Strength |
|-------|------|-------|----------|
| Composer 1.5 | Low | Fast | Day-to-day tasks, tightly scoped changes, single-module edits |
| Claude Sonnet 4.6 | Medium | Medium | Multi-file work within 1-2 modules, moderate complexity refactors |
| Claude Opus 4.6 | High | Slow | Cross-module refactors (3+ modules), risky migrations, architectural decisions, vague requirements |

Decision criteria:
- **How many modules are touched?** 1 module → Composer. 2 modules → Sonnet. 3+ modules → Opus.
- **Is it a pure refactor or new architecture?** Refactor with clear plan → Sonnet. New design decisions needed → Opus.
- **Risk level?** Breaking changes, migrations, security-sensitive → Opus. Safe additive changes → Composer/Sonnet.
- **Plan clarity?** Plan is detailed with exact file lists and code examples → Sonnet/Composer can handle it. Plan is high-level or ambiguous → Opus.