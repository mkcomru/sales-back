Explore the referenced code area for design improvements and simplification opportunities.

## Process

1. **Read the code** — trace the full flow end-to-end across modules
2. **Identify friction** — what's unnecessarily complex, duplicated, or tightly coupled?
3. **Find the root cause** — why does the friction exist? Is it accidental complexity or essential?
4. **Evaluate alternatives** — what design would eliminate the problem, not just patch it?
5. **Assess trade-offs** — migration cost, breaking changes, what gets simpler vs what gets harder

## Output

Report as text, no code changes. Structure:

- **Current design** — how it works now (brief)
- **Core problem** — the root cause of complexity, not symptoms
- **Design direction** — the simplification that addresses it
- **What it eliminates** — concrete list of things that go away
- **Migration risk** — what could break, rough effort estimate
- **Test safety net** — what must be tested BEFORE refactoring starts (see below)

## Test Safety Net (Required Section)

Before any refactor begins, identify the minimum test coverage that protects against regressions. Structure:

- **Critical paths** — list specific files/functions that carry core business logic through the refactored area. These MUST have tests before any code is moved or rewritten.
- **Contract boundaries** — public API surfaces (endpoints, service method signatures, shared schemas) that other modules or consumers depend on. Tests here guarantee the refactor doesn't silently break callers.
- **State transitions** — any logic involving status changes, side effects, or multi-step workflows (e.g., order assignment, handoff, stage updates). These are the most fragile under refactoring.
- **Edge cases already known** — bugs, race conditions, or tricky branches that exist today. If they're not tested, the refactor WILL reintroduce them.

For each item, specify:
1. **File** — exact path to the code that needs test coverage
2. **What to test** — the behavior or invariant, not implementation details

If the area already has sufficient test coverage, state that explicitly and point to the existing test files.

## Rules

- Don't propose quick hacks that only address the immediate symptom
- Don't suggest adding more abstraction layers unless they remove existing ones
- Focus on designs that make both current and future work simpler
- If the current design is actually fine, say so — not everything needs refactoring
