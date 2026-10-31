# 036 — Redis Cache Framework (Project-Wide)

## Objective

Build a lightweight, project-wide caching layer in `libs/common` on top of the existing Redis connection. Three abstractions: `CacheKey` (value object), `CacheService` (`get_or_compute` + invalidation), `RedisClient` (generic KV wrapper). Each module defines its own `KeyManager` with module-specific keys. No external libraries — uses `redis.asyncio` + `pydantic.TypeAdapter` already in the project.

Also: migrate backend's `RedisKVClient` into common as a generic `RedisClient`, since it's a natural peer to the existing `RedisStreamsBroker` in `common.events.adapters`.

## Why this matters

Every inbound customer message triggers `AgentContextAssembler.build()`, which queries DB for prompt template, company specification, capabilities, and tools — data that changes maybe once a week. With ~N messages per conversation and ~M active conversations, that's N×M redundant DB round-trips per day for static data.

Beyond backend, transports could cache connector configs, and sales-agent could cache prompt rendering. Having the framework in common means any module can opt in with `from common.cache import CacheService, CacheKey`.

What becomes possible after implementation:
- Sub-millisecond context assembly for the hot path (prompt + company spec + capabilities)
- Any module can introduce caching with zero new dependencies
- Future: connectors cache transport configs, eliminating redundant backend round-trips
- Future: replace some Redis Streams fan-out with simple cache invalidation for simpler use cases

## Invalidation Strategy

**Every cached key MUST have explicit invalidation in its mutation path.** TTL is a safety net (self-healing if an invalidation is missed), not the primary mechanism. This is manageable because invalidation calls go into the same encapsulated service/repo methods that already handle dependent data — it's one extra line per mutation, not a separate concern.

### Rules

1. **Always invalidate explicitly.** Every `get_or_compute` call implies a corresponding `invalidate` call somewhere in a mutation method. No exceptions, no "TTL-only" keys.

2. **Pattern invalidation MUST be scoped to `company_id`.** Never `pulse:backend:orders:*` (cross-company). Always `pulse:backend:company:{company_id}:*`. Dropping cache for one company is a negligible hit. Dropping an entire domain for all companies is a production spike waiting to happen.

3. **Prefer targeted invalidation over pattern.** Use `cache.invalidate(KeyManager.order_detail(company_id, order_id))` when you know the exact key. Use `cache.invalidate_pattern(KeyManager.company_pattern(company_id))` only when a mutation affects an unpredictable set of keys for that company.

4. **TTL as safety net.** Every key has a TTL so stale data self-heals if an invalidation is missed. This is defense-in-depth, not the strategy.

### Key hierarchy

Structure keys with `company_id` early so pattern invalidation is always company-scoped:

```
pulse:{module}:company:{company_id}:{entity}:{params}
pulse:backend:company:{company_id}:spec
pulse:backend:company:{company_id}:caps
pulse:backend:company:{company_id}:orders:list:{limit}:{offset}
pulse:backend:company:{company_id}:orders:detail:{order_id}
```

Pattern `pulse:backend:company:{company_id}:*` wipes everything for one company. Pattern `pulse:backend:company:{company_id}:orders:*` wipes only orders for one company. Cross-company patterns are forbidden.

---

## Phase 1: Cache infrastructure in `libs/common`

**Creates:**
- `libs/common/src/common/cache/__init__.py` — public exports
- `libs/common/src/common/cache/client.py` — `RedisClient` (generic async Redis KV wrapper)
- `libs/common/src/common/cache/service.py` — `CacheService` (`get_or_compute`, `invalidate`, `invalidate_pattern`)
- `libs/common/src/common/cache/types.py` — `CacheKey` NamedTuple

**Modifies:**
- `libs/common/src/common/__init__.py` — re-export `CacheKey`, `CacheService`, `RedisClient`

### 1.1 `types.py` — CacheKey

```python
from typing import NamedTuple

class CacheKey(NamedTuple):
    key: str
    ttl: int
```

### 1.2 `client.py` — RedisClient

Generic async Redis KV wrapper. Peer to `RedisStreamsBroker` — same Redis instance, different access pattern.

```python
import redis.asyncio as aioredis

class RedisClient:
    def __init__(self, redis_url: str, *, decode_responses: bool = True) -> None:
        self._client: aioredis.Redis = aioredis.from_url(redis_url, decode_responses=decode_responses)

    async def get(self, key: str) -> str | None: ...
    async def set(self, key: str, value: str | bytes, *, ex: int | None = None) -> None: ...
    async def delete(self, *keys: str) -> None: ...
    async def getdel(self, key: str) -> str | None: ...
    async def scan_delete(self, pattern: str) -> int: ...
    async def close(self) -> None: ...
```

This is a superset of the current `RedisKVClient`. All current methods (`set_with_ttl`, `get_and_delete`) map directly to `set(ex=)` and `getdel()`. The domain-specific `WsTicketPayload` typing stays in backend (see Phase 2).

### 1.3 `service.py` — CacheService

```python
from collections.abc import Awaitable, Callable
from pydantic import TypeAdapter

from common.cache.client import RedisClient
from common.cache.types import CacheKey

class CacheService:
    def __init__(self, client: RedisClient) -> None:
        self._client = client

    async def get_or_compute[T](
        self,
        cache_key: CacheKey,
        loader: Callable[[], Awaitable[T]],
        response_type: type[T],
    ) -> T:
        raw = await self._client.get(cache_key.key)
        if raw is not None:
            return TypeAdapter(response_type).validate_json(raw)
        result = await loader()
        serialized = TypeAdapter(response_type).dump_json(result)
        await self._client.set(cache_key.key, serialized, ex=cache_key.ttl)
        return result

    async def invalidate(self, *keys: CacheKey) -> None:
        if keys:
            await self._client.delete(*(k.key for k in keys))

    async def invalidate_pattern(self, pattern: str) -> None:
        await self._client.scan_delete(pattern)
```

### 1.4 Package exports

```python
# common/cache/__init__.py
from common.cache.client import RedisClient
from common.cache.service import CacheService
from common.cache.types import CacheKey

__all__ = ["CacheKey", "CacheService", "RedisClient"]
```

**Dependencies:** `redis>=5.0` and `pydantic>=2.9` — both already in `common` pyproject.toml.

### 1.5 Testing infrastructure: `InMemoryRedisClient`

Following the existing pattern (`common/events/testing/InMemoryBroker`), create an in-memory fake that implements the same interface as `RedisClient` — no real Redis needed in tests.

**Creates:**
- `libs/common/src/common/cache/testing.py` — `InMemoryRedisClient`

```python
class InMemoryRedisClient:
    """In-memory Redis replacement for testing. Same interface as RedisClient."""

    def __init__(self) -> None:
        self._store: dict[str, tuple[str | bytes, float | None]] = {}  # key -> (value, expires_at)

    async def get(self, key: str) -> str | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if expires_at is not None and time.monotonic() > expires_at:
            del self._store[key]
            return None
        return value

    async def set(self, key: str, value: str | bytes, *, ex: int | None = None) -> None:
        expires_at = (time.monotonic() + ex) if ex else None
        self._store[key] = (value, expires_at)

    async def delete(self, *keys: str) -> None:
        for k in keys:
            self._store.pop(k, None)

    async def getdel(self, key: str) -> str | None:
        entry = self._store.pop(key, None)
        if entry is None:
            return None
        return entry[0]

    async def scan_delete(self, pattern: str) -> int:
        # Convert glob pattern to fnmatch
        import fnmatch
        matched = [k for k in self._store if fnmatch.fnmatch(k, pattern)]
        for k in matched:
            del self._store[k]
        return len(matched)

    async def close(self) -> None:
        self._store.clear()

    # --- Test helpers ---
    def keys(self) -> list[str]:
        return list(self._store.keys())

    def clear(self) -> None:
        self._store.clear()
```

### 1.6 Unit tests for `CacheService`

**Creates:**
- `libs/common/tests/cache/__init__.py`
- `libs/common/tests/cache/test_service.py`
- `libs/common/tests/cache/test_client.py`

#### `test_service.py` — test matrix

| Test | Verifies |
|------|----------|
| `test_cache_miss_calls_loader` | Loader is called, result is returned and stored |
| `test_cache_hit_skips_loader` | Loader is NOT called, cached value is returned |
| `test_cache_hit_returns_correct_type` | Deserialization produces the exact Pydantic model |
| `test_list_type_serialization` | `list[SomeModel]` round-trips correctly via `TypeAdapter` |
| `test_dict_type_serialization` | `dict` round-trips correctly (for `company_spec`) |
| `test_ttl_is_set` | Value is stored with correct TTL from `CacheKey` |
| `test_loader_error_does_not_cache` | If loader raises, nothing is written to cache |
| `test_invalidate_single_key` | Key is removed after `invalidate()` |
| `test_invalidate_multiple_keys` | Multiple keys removed in one call |
| `test_invalidate_pattern` | Glob pattern removes matching keys, leaves non-matching |
| `test_invalidate_pattern_company_scoped` | Pattern with `company_id` only affects that company's keys |

All tests use `InMemoryRedisClient` — no Redis server, no Docker, instant execution.

#### `test_client.py` — InMemoryRedisClient self-tests

| Test | Verifies |
|------|----------|
| `test_get_set_round_trip` | Basic set + get returns correct value |
| `test_get_missing_key` | Returns `None` for absent key |
| `test_delete` | Key is gone after delete |
| `test_getdel` | Returns value and removes it atomically |
| `test_scan_delete_pattern` | Glob matching works correctly |
| `test_ttl_expiry` | Expired keys return `None` |

---

## Phase 2: Migrate backend's `RedisKVClient` → `common.cache.RedisClient`

**Modifies:**
- `apps/backend/src/backend/services/redis.py` — replace `RedisKVClient` with thin wrapper around `common.cache.RedisClient`, keep `WsTicketPayload` and ticket-specific helpers here (they're backend-specific domain logic)
- `apps/backend/src/backend/main.py` — init `RedisClient` from common, pass to both `CacheService` and backend's ticket helpers
- `apps/backend/src/backend/modules/chat/dependencies.py` — update `RedisClientDep` import, add `CacheDep`

### What stays in backend

`WsTicketPayload` and the WebSocket ticket set/get logic are backend-specific domain concerns. They stay in `backend/services/redis.py` but now use `common.cache.RedisClient` under the hood instead of raw `redis.asyncio`:

```python
# backend/services/redis.py — after migration
from common.cache import RedisClient

class WsTicketPayload(BaseModel):
    user_id: int
    company_id: int
    role: str

class WsTicketStore:
    def __init__(self, client: RedisClient) -> None:
        self._client = client

    async def set_ticket(self, key: str, value: WsTicketPayload, ttl: int) -> None:
        await self._client.set(key, value.model_dump_json(), ex=ttl)

    async def get_and_delete_ticket(self, key: str) -> WsTicketPayload | None:
        raw = await self._client.getdel(key)
        if raw is None:
            return None
        return WsTicketPayload.model_validate_json(raw)
```

### Import migration (3 files)

| File | Before | After |
|------|--------|-------|
| `main.py` | `from src.backend.services.redis import RedisKVClient` | `from common.cache import RedisClient` |
| `chat/dependencies.py` | `from src.backend.services.redis import RedisKVClient, get_redis_client` | `from common.cache import RedisClient` + local getter |
| `chat/routers.py` | `from src.backend.services.redis import WsTicketPayload` | No change (stays in backend) |

**Dependencies:** Phase 1 (`common.cache.RedisClient`).

---

## Phase 3: Agent context partial caching (highest impact)

**Modifies:**
- `apps/backend/src/backend/modules/messages/context_assembly.py` — inject `CacheService`, cache slow-changing parts of `build()`
- `apps/backend/src/backend/modules/messages/dependencies.py` — pass `CacheService` to `AgentContextAssembler`

**Creates:**
- `apps/backend/src/backend/services/cache_keys.py` — backend's `KeyManager` with all backend-specific cache keys

### KeyManager (backend-specific)

```python
# backend/services/cache_keys.py
from common.cache import CacheKey

class KeyManager:
    _PREFIX = "pulse:backend"

    # --- Context assembly keys ---

    @staticmethod
    def agent_prompt() -> CacheKey:
        return CacheKey(f"{KeyManager._PREFIX}:prompts:agent", ttl=3600)

    @staticmethod
    def company_spec(company_id: int) -> CacheKey:
        return CacheKey(f"{KeyManager._PREFIX}:company:{company_id}:spec", ttl=3600)

    @staticmethod
    def company_capabilities(company_id: int) -> CacheKey:
        return CacheKey(f"{KeyManager._PREFIX}:company:{company_id}:caps", ttl=3600)

    # --- Company-scoped invalidation patterns ---

    @staticmethod
    def company_all_pattern(company_id: int) -> str:
        return f"{KeyManager._PREFIX}:company:{company_id}:*"
```

### What gets cached in `build()`

| Data | Key | TTL | Explicit invalidation |
|------|-----|-----|----------------------|
| Agent prompt | `pulse:backend:prompts:agent` | 3600s | `PromptsService` on prompt update/delete |
| Company spec | `pulse:backend:company:{id}:spec` | 3600s | `CompaniesService` on company/FAQ/tool/field/category CRUD |
| Active capabilities | `pulse:backend:company:{id}:caps` | 3600s | `IntegrationRepository` on integration config change |

### What stays uncached

- `history` — changes every message
- `customer_answers` / `order_fields` / `extra_fields` — change on tool calls
- `langfuse_session_id` — per-conversation

**Dependencies:** Phase 1 (`CacheService`, `CacheKey`), Phase 2 (`RedisClient` wired in lifespan).

---

## Phase 4: Explicit invalidation in mutation paths

**Modifies:**
- `apps/backend/src/backend/modules/companies/service.py` — invalidate `company:spec` on update/delete/FAQ CRUD
- `apps/backend/src/backend/modules/prompts/service.py` — invalidate `prompts:agent` on prompt update/delete
- `apps/backend/src/backend/modules/integrations/repository.py` — invalidate `company:caps` on config change
- `apps/backend/src/backend/services/cache_keys.py` — add any missing invalidation patterns

### Invalidation map

All invalidations are **targeted** (exact key) unless noted as pattern. Pattern is always company-scoped.

| Mutation | Invalidates | Type |
|----------|-------------|------|
| `CompaniesService.update_company(company_id)` | `KeyManager.company_spec(company_id)` | Targeted |
| `CompaniesService.delete_company(company_id)` | `KeyManager.company_all_pattern(company_id)` | Pattern (company-scoped) |
| `CompaniesService.create/update/delete_faq(company_id)` | `KeyManager.company_spec(company_id)` | Targeted |
| `PromptsService.update/delete_prompt` | `KeyManager.agent_prompt()` | Targeted |
| Integration config changes for company | `KeyManager.company_capabilities(company_id)` | Targeted |
| Tool/field/category CRUD for company | `KeyManager.company_spec(company_id)` | Targeted |

**Dependencies:** Phase 3 (keys defined in `KeyManager`, `CacheService` injected into services).

---

## Phase 5 (optional, later): Router-level response caching + other modules

**Backend endpoints** — wrap order/chat/customer GET endpoints with `cache.get_or_compute()`.

**Transport modules** — each defines its own `KeyManager` locally and uses `CacheService` from common. E.g.:

```python
# telegram_module/cache_keys.py
from common.cache import CacheKey

class KeyManager:
    _PREFIX = "pulse:telegram"

    @staticmethod
    def connector_config(connector_id: str) -> CacheKey:
        return CacheKey(f"{KeyManager._PREFIX}:connector:{connector_id}:config", ttl=1800)
```

**Dependencies:** Phase 1.

---

## Files summary

| Phase | File | Action |
|-------|------|--------|
| 1 | `libs/common/src/common/cache/__init__.py` | **Create** |
| 1 | `libs/common/src/common/cache/types.py` | **Create** — `CacheKey` |
| 1 | `libs/common/src/common/cache/client.py` | **Create** — `RedisClient` |
| 1 | `libs/common/src/common/cache/service.py` | **Create** — `CacheService` |
| 1 | `libs/common/src/common/cache/testing.py` | **Create** — `InMemoryRedisClient` |
| 1 | `libs/common/src/common/__init__.py` | Modify — add exports |
| 1 | `libs/common/tests/cache/__init__.py` | **Create** |
| 1 | `libs/common/tests/cache/test_service.py` | **Create** — `CacheService` unit tests |
| 1 | `libs/common/tests/cache/test_client.py` | **Create** — `InMemoryRedisClient` self-tests |
| 2 | `apps/backend/src/backend/services/redis.py` | Modify — use `common.cache.RedisClient`, extract `WsTicketStore` |
| 2 | `apps/backend/src/backend/main.py` | Modify — init `RedisClient` + `CacheService` from common |
| 2 | `apps/backend/src/backend/modules/chat/dependencies.py` | Modify — update imports, add `CacheDep` |
| 3 | `apps/backend/src/backend/services/cache_keys.py` | **Create** — backend `KeyManager` |
| 3 | `apps/backend/src/backend/modules/messages/context_assembly.py` | Modify — use `CacheService` |
| 3 | `apps/backend/src/backend/modules/messages/dependencies.py` | Modify — pass `CacheService` to assembler |
| 4 | `apps/backend/src/backend/modules/companies/service.py` | Modify — add invalidation |
| 4 | `apps/backend/src/backend/modules/prompts/service.py` | Modify — add invalidation |
| 4 | `apps/backend/src/backend/modules/integrations/repository.py` | Modify — add invalidation |
| 5 | Various router/service files across modules | Modify — as needed |

---

## Recommended model for execution

**Phase 1:** Claude Sonnet 4.6 — creates a new package in `libs/common`, needs to follow existing patterns (`events/` package structure, `__init__.py` re-exports). Clean, isolated, but touches shared library.

**Phase 2:** Claude Sonnet 4.6 — migration across 2 modules (common + backend), import rewiring, needs to preserve backward compat for `WsTicketPayload`.

**Phase 3:** Composer 1.5 — backend-only, 3 files, clear pattern from the plan.

**Phase 4:** Composer 1.5 — small independent changes in 3 services, each is a 2-line addition.

**Phase 5:** Composer 1.5 per module/endpoint — each is independent.
