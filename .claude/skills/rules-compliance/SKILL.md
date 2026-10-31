---
name: rules-compliance
description: Run after any implementation touching 5+ files. Audits changed files against all .cursor/rules/*.mdc and fixes violations.
allowed-tools: Read, Grep, StrReplace
---

# Rules Compliance Check

Post-implementation audit against project rules. Run after any change touching **5+ files** or after `/implement-plan`.

## Procedure

1. Read **every** `.mdc` file in `.cursor/rules/`. Do not enumerate what to check — the rules themselves are the source of truth.

2. Identify all files changed in the current session — use the files already in context from the ongoing work; do not run git to discover changes.

3. For each changed file, verify compliance with **everything** stated in the rules you read. Report violations grouped by rule file, with file + line references.

4. Fix every violation you find. If a fix has non-trivial side effects or risk, flag it to the user instead of applying silently.

## Output Format

```
## Rules Compliance Report

### Violations Found
1. **[rule-file]** `path/to/file.py:42` — description of violation
   → Fix: description of fix applied (or "Flagged — requires user decision")

### Clean
All other checked files comply.
```

If zero violations: respond with "All files pass rules compliance check."
