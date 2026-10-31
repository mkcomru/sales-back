# Cursor Commands

Reusable prompts for common development workflows. Invoke with `/command-name` in chat.

## Planning Workflow

| Command | Purpose | Input |
|---------|---------|-------|
| `/investigate` | Explore codebase, trace flows, understand current state | Question in message |
| `/requirements` | **Iterative Q&A** to create requirements doc (what to build, not how) | Task description |
| `/plan` | Create numbered plan from discussion | Context in chat |
| `/validate-plan` | Check plan against actual code, find gaps | Plan file tagged |
| `/assess-plan` | Critical analysis: pros/cons, worth it? | Plan file tagged |
| `/implement-plan` | Execute plan tasks in order | Plan file tagged |
| `/create-test-scenarios` | Generate manual test script for implemented plan | Plan file tagged |

### Typical Flow

```
1. "How does auth work?" → /investigate
2. "Let's refactor it" → /plan
3. @plans/xxx.md → /validate-plan
4. @plans/xxx.md → /assess-plan
5. @plans/xxx.md → /implement-plan
6. @plans/xxx.md → /create-test-scenarios
```

### Requirements Flow (for complex/ambiguous tasks)

```
1. "Custom stages with auto-transitions" → /requirements
2. [Iterative Q&A rounds until requirements are clear]
3. Hand off to developer with complete requirements doc
```

Use `/requirements` when:
- Task has many business logic decisions
- Multiple valid approaches with trade-offs
- Will be handed off to another developer
- Need to document "why" not just "what"

## Quality Commands

| Command | Purpose | Input |
|---------|---------|-------|
| `/rules-check` | Audit changed files against project rules (data-consistency, FastAPI, etc.) | After implementation |

## Utility Commands

| Command | Purpose | Input |
|---------|---------|-------|
| `/report` | Quick text analysis without files | Question in message |
| `/squash-pr-message` | Combine commits into one conventional message | Commit messages |

## Usage Examples

**Investigate a problem:**
```
Is it possible to debounce messages in backend instead of sales-agent?
/investigate
```

**Create a plan:**
```
Let's move message persistence to backend
/plan
```

**Validate before implementing:**
```
@plans/013-message-persistence-separation.md
/validate-plan
```

**Get honest assessment:**
```
@plans/013-message-persistence-separation.md
/assess-plan
```

**Start implementation:**
```
@plans/013-message-persistence-separation.md
/implement-plan
```

**Create test scenarios after implementation:**
```
@plans/027-tasks-and-reminders-system.md
/create-test-scenarios
```
