# Rollback Plan: Remove Broadcast MVP Code

## Objective

Remove all temporary broadcast MVP code added for proof-of-value testing after the experiment is complete. This code was added as a throwaway implementation to assess conversion impact before investing in the full broadcast domain architecture (see plan 005).

## Context

The broadcast MVP was implemented as a rapid experiment (plan 006) to validate the value of mass Telegram messaging. It includes:
- CLI scripts for manual broadcasts
- Temporary API endpoints in sales-agent
- HTML form interface
- Service layer for broadcast handling

Once the experiment is complete and we decide on the production architecture, all MVP code should be removed to avoid technical debt.

## Files to Remove

### Sales Agent Module

1. **`apps/sales-agent/src/sales_agent/api/`** (entire directory)
   - `__init__.py` - API module init
   - `routes.py` - Broadcast API routes and HTML form
   - `broadcast_service.py` - Broadcast service implementation
   - `schemas.py` - Broadcast request/response schemas

2. **`apps/sales-agent/src/sales_agent/main.py`**
   - Remove broadcast router import and inclusion (lines ~549-551)

### Scripts (Optional - may keep for emergency use)

3. **`scripts/broadcast_mvp/`** (entire directory)
   - `send_manual_broadcast.py` - CLI script for manual broadcasts
   - `enrich_recipients.py` - Script to enrich CSV with Telegram names
   - `analyze_reply_rate.py` - Script to analyze reply rates
   - `README.md` - Documentation
   - Sample CSV files

**Note**: Consider keeping scripts in a `scripts/archive/` or `scripts/deprecated/` directory for emergency use, or remove entirely if production broadcast system is in place.

## Search Pattern

All temporary code is marked with:
```
BROADCAST-MVP-TODO: Remove this ...
```

To find all instances:
```bash
grep -r "BROADCAST-MVP-TODO" apps/sales-agent/
grep -r "BROADCAST-MVP-TODO" scripts/broadcast_mvp/
```

## Rollback Steps

1. **Verify experiment completion**
   - Confirm broadcast MVP experiment is complete
   - Ensure production broadcast system (plan 005) is implemented or decision made
   - Backup any important data/logs from MVP runs

2. **Remove sales-agent API code**
   ```bash
   # Remove API directory
   rm -rf apps/sales-agent/src/sales_agent/api/
   
   # Edit main.py to remove broadcast router
   # Remove lines ~549-551 in apps/sales-agent/src/sales_agent/main.py
   ```

3. **Remove scripts (if not keeping for emergencies)**
   ```bash
   rm -rf scripts/broadcast_mvp/
   ```

4. **Verify no broken imports**
   ```bash
   cd apps/sales-agent
   uv run ruff check .
   uv run pyright
   ```

5. **Test application startup**
   ```bash
   # Ensure sales-agent starts without errors
   uv run --package sales-bot uvicorn sales_agent.main:app --reload
   ```

6. **Update dependencies (if needed)**
   - Check if `python-multipart` is still needed (only used by broadcast endpoint)
   - Remove from `apps/sales-agent/pyproject.toml` if not used elsewhere

## Dependencies to Review

- `python-multipart` in `apps/sales-agent/pyproject.toml` - Only needed for broadcast file uploads

## Related Plans

- **Plan 006**: Rapid Broadcast MVP Plan (implementation)
- **Plan 005**: Telegram Broadcasts (production architecture)

## Roll Forward Path

If broadcast MVP proves valuable:
1. Implement production-grade architecture from plan 005
2. Remove MVP code using this rollback plan
3. Migrate any useful patterns/logic to production system

If broadcast MVP doesn't prove valuable:
1. Remove MVP code immediately using this rollback plan
2. Archive learnings in plan 006

## Verification Checklist

- [ ] All `BROADCAST-MVP-TODO` markers removed
- [ ] `apps/sales-agent/src/sales_agent/api/` directory deleted
- [ ] Broadcast router removed from `main.py`
- [ ] Application starts without errors
- [ ] No broken imports or references
- [ ] Linter passes
- [ ] Type checker passes
- [ ] Scripts removed or archived (if applicable)
- [ ] Dependencies cleaned up (`python-multipart` if unused)

---

## Additional Temporary Code: Segment ID Workaround

### Context

A temporary workaround was added to extract `segment_id` from `ChatMessage.meta["chat_id"]` for prompt rendering. This calculates `segment_id = chat_id % 5` and passes it to Jinja templates in prompts loaded from the database.

### Files to Clean Up

1. **`apps/sales-agent/src/sales_agent/agents/pipeline.py`**
   - Remove `_extract_segment_id()` function (lines ~71-88)
   - Remove `segment_id` extraction and passing in:
     - `_invoke_category_expert()` - Remove segment_id from substitutions dict
     - Router prompt rendering (lines ~468-475) - Remove segment_id extraction and extra_substitutions
     - Qualifier prompt rendering (lines ~555-562) - Remove segment_id extraction and extra_substitutions

2. **`apps/sales-agent/src/sales_agent/services/prompt_formatter.py`**
   - Remove `extra_substitutions` parameter from `format_prompt()` method (lines ~31, ~49-51)
   - Revert to original signature without extra_substitutions

### Search Pattern

All temporary code is marked with:
```
# TODO: delete
```

To find all instances:
```bash
grep -r "# TODO: delete" apps/sales-agent/src/sales_agent/agents/pipeline.py
grep -r "# TODO: delete" apps/sales-agent/src/sales_agent/services/prompt_formatter.py
```

### Cleanup Steps

1. **Remove segment_id extraction function**
   ```python
   # Remove _extract_segment_id() function from pipeline.py
   ```

2. **Remove segment_id from prompt rendering**
   - Remove segment_id extraction calls in router, qualifier, and category_expert paths
   - Remove `extra_substitutions` parameter usage
   - Revert `PromptFormatter.format_prompt()` signature

3. **Verify prompts in DB**
   - Ensure prompts in database no longer reference `segment_id` variable
   - Or document that `segment_id` is a permanent feature if decision is made to keep it

### Notes

- This workaround was added to support segment-based prompt variations stored in the database
- If segment-based prompts prove valuable, consider implementing a proper segment management system instead of calculating from chat_id modulo
- The workaround only passes `segment_id` when `meta` and `chat_id` are present in ChatMessage history

