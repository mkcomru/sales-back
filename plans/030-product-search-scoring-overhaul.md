# 030 — Product Search: Scoring Overhaul

## Objective

Replace the current binary pass/fail product search with a score-based ranking algorithm that always returns top results. Simplify the tool interface to a single `query` string so the AI focuses on generating good keywords instead of guessing filter schemas.

## Why This Matters

Right now the AI frequently gets zero results because a single attribute mismatch eliminates a product entirely. Customers see "nothing found" when relevant products exist. The tool's `filters` object forces the AI to guess exact attribute keys and values — it often guesses wrong.

After this change:
- Product search always returns the best-available matches (top 3), never empty
- The AI sends a natural language query; the tool handles matching internally
- Keyword-rich product names/descriptions (which we enforce on clients) become the primary search signal
- Partial attribute overlap ranks products instead of eliminating them

## Design Decisions

- **Use `rapidfuzz` library** for scoring (Levenshtein, token_set_ratio, partial_ratio). Battle-tested, fast C-extension, handles Russian morphology variants naturally via token-based matching. No wheel reinvention.
- **Single `query` parameter** — remove `filters` and `limit` from the AI-facing schema. The tool extracts customer context internally from the ContextVar.
- **Always return results** — cap at 3, sorted by score. If everything scores low, still return top 3 with scores so the AI can hedge ("here are the closest options").
- **Combined scoring from all fields** — name, description, and attributes are all scored via `token_set_ratio` and their scores are summed into the final product score. Every field contributes; a product that matches on name AND description AND attributes ranks higher than one matching only on name. Long descriptions don't penalize because `token_set_ratio` measures overlap of token sets, not length ratio.
- **Rich queries are better** — the AI should extract all relevant keywords from conversation (features, preferences, budget, location, etc.) into the query. `token_set_ratio` handles extra tokens gracefully since it tests token-set intersection against each side independently. More relevant tokens = more chances to hit across name/description/attributes.

## Phase 1: Add `rapidfuzz` + New Scoring Engine

**Files:**
- `apps/sales-agent/pyproject.toml` — add `rapidfuzz` dependency
- `apps/sales-agent/src/sales_agent/agents/tools.py` — replace `_fuzzy_match`, `_match_attributes`, and `search_product` with score-based implementation

**Algorithm:**
1. Score ALL products in the catalog (no category filtering — category scoping is out of scope, will be a separate task)
2. For each product, compute combined score (0–300 range) by summing:
   - `token_set_ratio(query, product.name)` — 0–100, name contribution
   - `token_set_ratio(query, product.description)` — 0–100, description contribution
   - Best attribute match: `max(token_set_ratio(query, attr_text) for attr_text in stringified_attrs)` — 0–100. **Guard:** default 0 when attributes is empty/None
3. **Attribute value serialization:** list values like `["Кавказ", "Эльбрус"]` must be joined with spaces (`"Кавказ Эльбрус"`), not `str()` which produces bracket noise. Scalar values → `str(v)`.
4. If customer answers have structured fields matching product attribute keys, add bonus for value overlap (soft, not eliminative)
5. Sort by combined score descending, return top 3
6. Always return results — even if scores are low, the AI gets something to work with

**Removes:** `_fuzzy_match`, `_match_attributes`, `_normalize_text` functions, `category_id`/`filters`/`limit` params from `search_product`.

## Phase 2: Simplify Tool Schema + Description

**Files:**
- `apps/sales-agent/src/sales_agent/core/tools/registry.py` — update `TOOL_SCHEMAS["search_product"]`, `TOOL_DESCRIPTIONS["search_product"]`, simplify `_create_search_product_handler` (remove `category_id` param, pass only `query` to `search_product`)

**New schema:**
```json
{
  "type": "object",
  "properties": {
    "query": {
      "type": "string",
      "description": "Search keywords: product name, key features, or what the customer is looking for"
    }
  },
  "required": ["query"]
}
```

**New description:** Guide the AI to pack the query with all relevant keywords from conversation — customer preferences, desired features, mentioned names, budget range, etc. Richer query = better ranking. Instruct explicitly: query must be at least 3+ words, never pass single characters or empty strings.

## Phase 3: Verification

- Run `uv run ruff format . && uv run ruff check --fix` from sales-agent root
- Run existing tests — **no existing tests reference `search_product`**, so no breakage expected from function changes
- Manual test with a few product catalogs to verify scoring produces sensible rankings

## Risks

- `rapidfuzz` is a C-extension — needs to compile in Docker. Should be fine (manylinux wheels exist), but verify in CI.
- Removing `filters` is a breaking change for the AI tool interface — any cached/in-flight tool calls with `filters` will get ignored. Low risk since tool schemas refresh per request.
- `token_set_ratio` on very short queries (1-2 chars) may produce noisy scores — enforce minimum query length in the tool (reject < 2 tokens) and instruct the AI via tool description to always provide rich keyword queries.
