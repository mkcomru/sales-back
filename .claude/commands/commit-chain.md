Organize all staged and unstaged changes into a logical chain of commits.

## Rules

1. Read `git status`, `git diff --stat`, and `git log --oneline -5` to understand the full picture.
2. Determine the right number of commits based on the change set:
   - 1-3 files in one module → 1 commit is fine
   - Multiple modules or layers → split by logical boundary
   - Aim for the minimum number where each commit is self-contained and reviewable
   - Never exceed 6 commits — if you need more, your grouping is too granular
3. Group files by logical layer, not alphabetically:
   - Common lib foundations first (types, enums, configs, shared utils)
   - Core models, repositories, exceptions next
   - Business logic (services, DI, registries) after
   - Routing, wiring, and app-level registration
   - Docs, plans, rules, stubs last
4. Each commit must be self-contained — no forward references to files that don't exist yet.
5. Use conventional commit format matching the repo style (`feat(scope):`, `docs:`, `refactor:`, etc.).
6. Commit message: 1 summary line + 2-4 bullet lines of what's inside. No fluff.
7. Run all commits sequentially, verify clean working tree at the end.
