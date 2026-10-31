Look at all staged and unstaged changes (`git status`, `git diff`, `git diff --cached`) to understand what has changed.

Based on the changes, propose a commit message in Conventional Commits format. The message must be in English.

**Format rules:**
- Subject line: `type(scope): concise summary` (max 72 chars)
- Body: bullet list of specific changes — what was added/changed/removed and why
- No Co-Authored-By lines
- Types: `feat`, `fix`, `refactor`, `chore`, `docs`, `test`, `perf`

**Good subject line examples:**
- `feat(backend): add Redis KV client for WS ticket storage`
- `fix(chat): prevent duplicate broadcast on message ingest`
- `refactor(auth): extract token validation into dependency`

**Body rules:**
- Each bullet = one concrete change, not a vague summary
- Mention file/module if it helps locate the change
- Include "why" only if it's not obvious from the subject

Show the proposed commit message to the user and ask them to:
1. Approve it as-is
2. Edit it and provide a corrected version
3. Cancel (stop the process entirely)

Wait for the user's response before proceeding.

Once approved, stage all changes and create the commit:
```
git add .
git commit -m "<approved message>"
```

If the commit fails due to a linter or pre-commit hook:
- Read the hook output carefully
- Fix all reported issues (formatting, linting errors, type errors, etc.)
- Do NOT use --no-verify
- Re-run the commit with the same commit message

If fixing linter issues requires additional changes, make those changes silently, then re-attempt the commit.
