Create a requirements document through iterative Q&A process. This is NOT an implementation plan — it captures WHAT to build and decisions made, not HOW to code it.

## Language

**Derive language from chat context** — Write the document in the same language the user uses in conversation. If user writes in Russian, document is in Russian. If in English, document is in English.

## Process

1. **Create initial file** — Based on chat context/referenced docs, create a **minimal** requirements file:
   - Objective (1-2 sentences max)
   - Why We're Doing This (auto-generated, brief)
   - Context (only essential background)
   - What We're Building (bullet points, no excessive detail)
   
   Keep it short and scannable. No elaborate specifics — just enough to confirm understanding. Details come later through Q&A.

2. **Ask questions in rounds** — After user confirms/corrects the base, ask GLOBAL questions from developer's perspective:
   - Business logic and product decisions
   - Architecture and design choices
   - Edge cases and conflict resolution
   - What happens when X? What if Y?
   
   NOT about code implementation details.
   
   **Use the AskQuestion tool** for questions that have discrete options (e.g. "Option A vs Option B", yes/no decisions, picking from a list). Always include an **"Other"** option so the user can give a free-form answer in chat; interpret that answer and continue with classic follow-up questions only when needed to clarify their custom choice. Fall back to plain text questions only when the decision truly cannot be meaningfully expressed as options, even with an "Other" choice.

3. **Iterate** — After answers, update the document with decisions and ask next round of questions. Continue until only minor details remain.

4. **Finalize** — Add module locations (where code goes), collected questions section, scope.

## Document Structure

```markdown
# NNN — Title

> **This is a requirements document**, not a step-by-step implementation plan...

## Objective
## Why We're Doing This (auto-generated, see below)
## Context  
## What We're Building (functionality sections)
## Decisions (made during Q&A)
## Module Structure (where each piece lives)
## API Endpoints (with module locations)
## Open Questions (for developer)
## Questions Addressed During Design
## Scope
```

(Section names adapt to user's language from chat context)

## "Why We're Doing This" Section (Required, Auto-Generated)

Generate this section automatically based on task context. Explain WHY this matters:
- What problem does it solve for end users?
- What value does it bring to the product from UI/UX perspective?
- What user workflows become possible/better after implementation?
- How does it improve the product experience?

This helps developers understand the PURPOSE beyond "just endpoints". They should feel the value of what they're building.

## Question Guidelines

- Group by theme (Syntax, Conflicts, Triggers, etc.)
- Be specific: "What happens when manager drags order back but system pushes forward?"
- Offer variants when applicable: "Option A: X, Option B: Y, Option C: Z"
- Ask about naming collisions, module placement, migration needs

## Finalization Checklist

- [ ] Disclaimer at top (this is requirements, not a plan)
- [ ] "Why We're Doing This" section (auto-generated, explains value for users/product)
- [ ] Module locations specified (where each piece lives)
- [ ] "Questions Addressed" section with VERBATIM questions (no answers — they're in the doc)
- [ ] Credit who worked on requirements (show the work done)
- [ ] Check if any GLOBAL questions remain or only minor details left

## Output

Create file: `plans/NNN-descriptive-name.md`

The document should be complete enough that another developer can implement it with minimal clarification, while having freedom in implementation details.
