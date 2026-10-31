# 032 — Integration Capability-Provider Pattern

## Objective

Establish a universal architecture for external service integrations (YClients, RetailCRM, AmoCRM, etc.) that allows any integration to replace or augment any part of the system — from agent tools to CRM data — without polluting the main codebase with conditionals.

## Why We're Doing This

- **Problem:** Clients use external services (YClients for scheduling, RetailCRM for CRM, AmoCRM for deals) and won't abandon them. Without seamless integration support, these are deal-breakers that cost us clients.
- **Value:** The platform becomes a hub that connects to whatever the client already uses. The sales agent can book appointments, pull products from external catalogs, sync customer data — all transparently. Admin panel shows data from the right source without custom UI per integration.
- **What becomes possible:** Adding a new integration = creating one self-contained module. No if/else in core code, no breakage risk, no architectural limits on what an integration can do. An integration can replace up to 50% of core functionality (products, staff, scheduling, orders) while the rest of the system stays untouched.

---

## Scope

**This plan covers ONLY the foundation infrastructure:**
- Common contracts (enums, schemas)
- Envelope encryption service
- Integration model, DI resolver, conflict detection
- Provider package structure and `BaseIntegrationClient`
- Agent context integration (capability-driven tool selection)
- Capability action endpoint scaffolding

**This plan does NOT implement any specific integration.** No YClients, no RetailCRM, no AmoCRM. Each integration is a separate plan that depends on this foundation. YClients appears in code examples below purely as design illustration — it is not in scope for implementation.

---

## Core Design Decisions

### 1. Service Inheritance over Provider/Protocol layers

Integration-specific behavior is implemented via service subclasses that override only the methods they need. The base service IS the builtin behavior. The override service IS the integration. No separate "Provider" abstraction layer.

```python
class ProductsService:
    async def list(self, company_id: int) -> list[Product]:
        return await self.repo.filter(company_id=company_id)

class YClientsProductsService(ProductsService):
    async def list(self, company_id: int) -> list[Product]:
        return await self.yclients.get_services(company_id)
    # search, create — inherited, work through DB as before
```

Three override modes:
- **Full replacement:** override returns data from external API instead of DB
- **Augmentation:** `super().method()` + side-effect (e.g., sync to CRM after creating order)
- **No change:** method not overridden, inherited as-is — automatic fallback

### 2. DI-level resolution

A generic `integration_aware()` dependency function resolves which service class to instantiate based on the company's active integrations. Routes and business logic never see conditionals.

```python
async def _resolve(base_cls: type[T], company_id: int) -> T:
    integrations = await IntegrationRepository().get_for_company(company_id)
    matches = []
    for integration in integrations:
        override = SERVICE_OVERRIDES.get((integration.provider_type, base_cls))
        if override:
            matches.append((integration, override))
    if len(matches) > 1:
        raise IntegrationConflictError(...)  # fail fast, never silently pick one
    if matches:
        return matches[0][1](integration=matches[0][0])
    return base_cls()


def integration_aware(base_cls: type[T]) -> Callable:
    """Public routes — company_id from CompanyViewerDep auth."""
    async def resolver(company_user: CompanyViewerDep) -> T:
        return await _resolve(base_cls, company_user.company_id)
    return resolver


def integration_aware_by_id(base_cls: type[T]) -> Callable:
    """Internal routes — company_id as path/query param or from request body."""
    async def resolver(company_id: int) -> T:
        return await _resolve(base_cls, company_id)
    return resolver


# Public routes
ProductsServiceDep = Annotated[ProductsService, Depends(integration_aware(ProductsService))]
# Internal routes
ProductsServiceInternalDep = Annotated[ProductsService, Depends(integration_aware_by_id(ProductsService))]
```

### 3. Incremental adoption

Each service is migrated to `integration_aware()` independently, only when there's a real integration that needs it. Unmigrated services keep working through DB with `@lru_cache` singletons. No big-bang migration required.

### 4. One integration per capability per company

A company can have multiple integrations (e.g., one for scheduling, another for customer data), but only one provider per capability. No composition of two providers for the same data domain.

---

## Phase 1: Common Contracts

**Module:** `libs/common`

**Creates:**
- `libs/common/src/common/integrations.py`:
  - `Capability` enum — `PRODUCTS`, `SCHEDULING`, `STAFF`, `CUSTOMER_DATA`, etc.
  - `CAPABILITY_TOOLS: dict[Capability, list[AvailableTool]]` — maps capabilities to agent tools they activate
  - No `ProviderType` enum — `provider_type` is a plain `str` on the `Integration` model. Each provider package defines its own type string (e.g., `"yclients"`) and registers overrides with it. This avoids modifying `libs/common` every time a new integration is added.

**Modifies:**
- `libs/common/src/common/tools.py` — no changes in this phase. New `AvailableTool` entries are added by integration-specific plans when they introduce capability-driven tools.
- `libs/common/src/common/models/outbound.py` — add `active_capabilities: list[str] = []` field to `AgentContext`

**Dependencies:** None.

---

## Phase 2: Envelope Encryption Service

**Module:** `libs/common` + `apps/backend`

**Goal:** A general-purpose credential encryption service using envelope encryption. Used by Integration credentials now, applicable to Connector secrets and any future sensitive data later.

**Scheme:**

```
MASTER_KEY (env var / KMS)
         |
         v
  Data Encryption Key (DEK) — unique per record
         |
         v
  encrypt(credentials_json, DEK) → encrypted_credentials
  encrypt(DEK, MASTER_KEY)       → encrypted_dek
```

DB stores: `encrypted_credentials` + `encrypted_dek`. To decrypt: `MASTER_KEY → DEK → credentials`.

**Creates:**
- `libs/common/src/common/crypto.py` — `EnvelopeEncryption` service:
  - `encrypt(plaintext: bytes) -> EncryptedPayload` — generates random DEK, encrypts data with DEK (AES-256-GCM), encrypts DEK with MASTER_KEY
  - `decrypt(payload: EncryptedPayload) -> bytes` — decrypts DEK with MASTER_KEY, decrypts data with DEK
  - `EncryptedPayload` — Pydantic model: `encrypted_data: str`, `encrypted_dek: str`, `nonce: str` (all base64)
  - `rotate_master_key(old_key, new_key)` — re-encrypts all DEKs with new master key without touching data

**Modifies:**
- `libs/common/src/common/config.py` — add `MASTER_ENCRYPTION_KEY` setting (required, loaded from env)

**Properties:**
- Master key rotation: re-encrypt DEKs only, data untouched
- Per-record isolation: each record has its own DEK, compromising one doesn't expose others
- Key revocation: delete the encrypted_dek to permanently revoke access
- Future: swap env-based MASTER_KEY for KMS (AWS KMS, Vault) without changing the API

**MVP:** `Fernet`-based symmetric encryption with `MASTER_ENCRYPTION_KEY` from env. Upgrade to KMS-backed later.

**Out of scope:** Migrating existing Connector secrets to envelope encryption (tracked separately).

**Dependencies:** None.

---

## Phase 3: Integration Model & DI Infrastructure

**Module:** `apps/backend`

**Creates:**
- `apps/backend/src/backend/modules/integrations/` — new module:
  - `models.py` — `Integration` model:
    - `id: int` (PK)
    - `company: ForeignKeyRelation[Company]`
    - `provider_type: str` (plain string, e.g. `"yclients"` — defined by provider packages, not an enum)
    - `credentials_encrypted: TextField` (API keys, tokens — encrypted via `EnvelopeEncryption` from Phase 2; stored as base64 `EncryptedPayload` JSON)
    - `credentials_dek: TextField` (encrypted DEK for this record's credentials)
    - `config: JSONField` (provider-specific non-secret settings — stored as plain JSON)
    - `enabled_capabilities: JSONField` (`list[str]` of Capability values)
    - `enabled: bool`
    - `Meta: unique_together = [("company", "provider_type")]`
  - `repository.py` — `IntegrationRepository`:
    - `get_for_company(company_id) -> list[Integration]` — all integrations where `enabled=True` for company (used by `_resolve()` to iterate and find matching override)
    - `get_by_capability(company_id, capability) -> Integration | None` — find integration whose `enabled_capabilities` includes the given capability (used by capability action endpoints)
  - `service.py` — `IntegrationService` (CRUD + credentials validation + capability conflict detection)
  - `schemas.py` — `IntegrationCreate`, `IntegrationUpdate`, `IntegrationResponse`
  - `routers.py` — `/companies/{company_id}/integrations` CRUD endpoints
  - `dependencies.py` — `IntegrationServiceDep`
  - `registry.py` — `SERVICE_OVERRIDES` dict, `register_override()`, `integration_aware()` generic dependency

- `apps/backend/migrations/models/` — migration for `Integration` table in `backend` schema

**Modifies:**
- `apps/backend/src/backend/modules/__init__.py` — register integrations router
- `apps/backend/src/backend/modules/core/models.py` — add `Integration` to model discovery

**Key implementation — `registry.py`:**

```python
from typing import Callable, TypeVar

SERVICE_OVERRIDES: dict[tuple[str, type], type] = {}

T = TypeVar("T")


def register_override(provider_type: str, base_cls: type, override_cls: type) -> None:
    SERVICE_OVERRIDES[(provider_type, base_cls)] = override_cls


async def _resolve(base_cls: type[T], company_id: int) -> T:
    from .repository import IntegrationRepository
    repo = IntegrationRepository()
    integrations = await repo.get_for_company(company_id)
    matches: list[tuple[Integration, type]] = []
    for integration in integrations:
        override = SERVICE_OVERRIDES.get((integration.provider_type, base_cls))
        if override:
            matches.append((integration, override))
    if len(matches) > 1:
        providers = [m[0].provider_type for m in matches]
        raise IntegrationConflictError(
            f"Multiple integrations override {base_cls.__name__}: {providers}"
        )
    if matches:
        return matches[0][1](integration=matches[0][0])
    return base_cls()


def integration_aware(base_cls: type[T]) -> Callable[..., T]:
    """Public routes — company_id from CompanyViewerDep."""
    async def resolver(company_user: CompanyViewerDep) -> T:
        return await _resolve(base_cls, company_user.company_id)
    return resolver


def integration_aware_by_id(base_cls: type[T]) -> Callable[..., T]:
    """Internal routes — company_id as parameter."""
    async def resolver(company_id: int) -> T:
        return await _resolve(base_cls, company_id)
    return resolver
```

**Conflict detection (two levels):**

1. **Capability overlap (CRUD time):** `IntegrationService.create()` / `.update()` checks if any existing enabled integration for the same company has overlapping `enabled_capabilities`. Raises `IntegrationCapabilityConflictError` with the conflicting provider name and capabilities. Prevents data-level conflicts before they exist.

   ```python
   existing = await self.repo.get_for_company(company_id)
   for other in existing:
       if other.id == integration_id:
           continue
       overlap = set(new_capabilities) & set(other.enabled_capabilities)
       if overlap:
           raise IntegrationCapabilityConflictError(
               f"Capabilities {overlap} already provided by {other.provider_type}"
           )
   ```

2. **Service override conflict (resolve time):** `_resolve()` collects ALL matching overrides across integrations. If more than one integration overrides the same service class, raises `IntegrationConflictError`. This catches code-level conflicts invisible at capability level (e.g., two integrations with different capabilities both overriding `CompaniesService`).

**Dependencies:** Phase 1 (`Capability` enum), Phase 2 (`EnvelopeEncryption` for credentials storage).

---

## Phase 4: Provider Package Structure (skeleton only)

**Module:** `apps/backend`

**Goal:** Create the directory structure, base client, and conventions for provider packages. **No concrete provider is implemented in this phase.**

**Creates:**
- `apps/backend/src/backend/integrations/` — top-level package for all provider implementations:
  - `__init__.py` — will import provider packages to trigger `register_override()` calls (empty initially)
  - `base.py` — `BaseIntegrationClient` with shared HTTP client logic:
    - async context manager
    - configurable auth headers
    - rate limiting (token bucket per provider instance)
    - retry with exponential backoff
    - structured error logging

Concrete provider packages follow this layout (created by integration-specific plans, NOT this plan):

```
integrations/<provider_name>/
├── __init__.py      # calls register_override() for each service override
├── client.py        # HTTP client subclassing BaseIntegrationClient
├── config.py        # Pydantic model for credentials/config validation
├── schemas.py       # response schemas from external API
└── services/        # override service classes
```

**Example — how a future provider registers overrides (illustrative, not implemented here):**

```python
# integrations/some_provider/__init__.py
from backend.modules.integrations.registry import register_override
from backend.modules.companies.service import CompaniesService
from .services.companies import SomeProviderCompaniesService

register_override("some_provider", CompaniesService, SomeProviderCompaniesService)
```

**Dependencies:** Phase 3 (`register_override()`, `Integration` model).

---

## Phase 5: Agent Context Integration

**Module:** `apps/backend` (messages module)

**Goal:** Make the agent automatically receive provider data and capability-driven tools without any changes in sales-agent.

**Modifies:**
- `apps/backend/src/backend/modules/messages/context_assembly.py`:
  - `_extract_enabled_tools()` — merge company/category tools with capability tools from `CAPABILITY_TOOLS` based on active integration capabilities
  - `AgentContextAssembler.build()` — pass `active_capabilities` in `AgentContext`; resolve CompaniesService inside `build()` using company_id (not at DI time)

- `apps/backend/src/backend/modules/messages/routers.py`:
  - Inbound message handler resolves CompaniesService after connector auth (company_id available from `ConnectorContext.company_id`), passes to assembler

**DI note:** `AgentContextAssembler` cannot use `integration_aware(CompaniesService)` as a Depends parameter because company_id is unknown at dependency resolution time for inbound routes (it comes from `ConnectorContext` after auth).

**Decision:** Assembler resolves internally — `build(company_id=...)` calls `_resolve(CompaniesService, company_id)` to get the right service instance. Assembler stays a single dependency injected via Depends, resolution is transparent to the caller.

**How it works at runtime (generic flow, no concrete provider needed to ship this phase):**

1. Message arrives for company with an integration (`enabled_capabilities: ["products", "scheduling"]`)
2. `AgentContextAssembler.build(company_id=42)` internally resolves `CompaniesService` via `_resolve()`
3. If an override exists → overridden service is used; if not → base service (current behavior)
4. `_extract_enabled_tools()` merges company/category tools with tools from `CAPABILITY_TOOLS` based on active capabilities
5. Agent receives enriched `AgentContext` — **zero changes in sales-agent pipeline**

**Dependencies:**
- Phase 1: `CAPABILITY_TOOLS` mapping, `AgentContext.active_capabilities` field
- Phase 3: `_resolve()` function, `IntegrationRepository.get_for_company()`
- Phase 4: `BaseIntegrationClient` (provider packages are created by integration-specific plans)

---

## Phase 6: Capability Action Endpoint Pattern (scaffolding only)

**Module:** `apps/backend` + `apps/sales-agent`

**Goal:** Establish the routing pattern for capability action endpoints. **No concrete endpoints are created in this phase** — they are added by integration-specific plans when they introduce new capabilities.

**Creates in backend:**
- `apps/backend/src/backend/modules/integrations/capability_routes.py` — internal router (service-key auth) with the generic resolution pattern:
  - Each capability endpoint resolves its provider via `IntegrationRepository.get_by_capability(company_id, capability)`, instantiates the provider client, calls the method. Returns 404 if no integration provides the requested capability.
  - **Concrete endpoints (e.g., scheduling/slots, staff/list) are added by integration-specific plans.**

**Creates in sales-agent:**
- `apps/sales-agent/src/sales_agent/agents/capability_tools.py` — empty module with the pattern for capability tool handlers:
  - Each handler calls the corresponding Backend capability endpoint.
  - **Concrete tool handlers are added by integration-specific plans.**

**Pattern example (illustrative — not implemented in this phase):**

```python
# Backend: capability_routes.py
@router.post("/capabilities/scheduling/slots")
async def get_slots(request: GetSlotsRequest, ...):
    integration = await repo.get_by_capability(request.company_id, Capability.SCHEDULING)
    if not integration:
        raise HTTPException(404, "No scheduling provider configured")
    client = build_client(integration)
    return await client.get_available_slots(...)

# Sales-agent: capability_tools.py
async def get_available_slots(context: AgentContext, ...):
    return await backend_client.post("/capabilities/scheduling/slots", ...)
```

**Modifies in sales-agent:**
- `apps/sales-agent/src/sales_agent/core/tools/registry.py` — no changes in this phase. New `ToolSpec` entries are added by integration-specific plans when they introduce capability tools.

**Dependencies:**
- Phase 3: `Integration` model, `IntegrationRepository.get_by_capability()`
- Phase 4: `BaseIntegrationClient` for building provider clients

---

## Migration Recipe: Making an Existing Service Integration-Aware

**This is a reference for integration-specific plans.** When a new integration needs to override an existing service, these are the steps that plan should include:

1. **Create override class** in the provider package:
   ```python
   # integrations/<provider>/services/products.py
   class <Provider>ProductsService(ProductsService):
       def __init__(self, *, integration: Integration, **kwargs):
           super().__init__(**kwargs)
           credentials = integration.decrypt_credentials()
           config = <Provider>Config(**credentials, **integration.config)
           self.client = <Provider>Client(config)

       async def list(self, company_id: int) -> list[Product]:
           return await self.client.get_products(company_id)
   ```

2. **Register override** in provider's `__init__.py`:
   ```python
   register_override("<provider>", ProductsService, <Provider>ProductsService)
   ```

3. **Switch dependency type** in the service's `dependencies.py` (one-time per service, not per integration):
   ```python
   # Before (singleton, no integration awareness)
   @lru_cache
   def products() -> ProductsService:
       return ProductsService()
   ProductsServiceDep = Annotated[ProductsService, Depends(products)]

   # After (integration-aware, per-request)
   ProductsServiceDep = Annotated[ProductsService, Depends(integration_aware(ProductsService))]
   ```

4. **Routes unchanged.** They still inject `ProductsServiceDep` and call the same methods.

---

## Candidate Services for Future Integration-Awareness

**Reference only.** These are the services most likely to be overridden by integrations. Actual migrations happen in integration-specific plans.

| Service | Likely Override Methods | Effort |
|---------|----------------------|--------|
| **CompaniesService** | `get_specification()` | Low — single method, spec dict shape unchanged |
| **ProductsService** | `list()`, `search()`, `get()` | Low — stateless reads |
| **StagesService** | `list()`, `get_for_company()` | Low — stateless reads |
| **OrdersService** | `create()` (augmented with sync side-effect) | Medium — write path, needs error handling |
| **UsersService** | Staff-related methods | Medium — affects assignment logic |

---

## Decided Risks

1. **Caching trade-off:** Integration-aware services are per-request, not `@lru_cache` singletons. Acceptable — services are stateless, instantiation is cheap. Optimize later with short-TTL integration config cache if needed.

2. **Internal route resolution:** Solved via `integration_aware_by_id()` — a second generic dependency that takes `company_id` as a parameter instead of extracting it from `CompanyViewerDep`. Both share `_resolve()` logic.

3. **External API failures:** No silent fallback to builtin. If the provider API is down, the operation fails explicitly. Unpredictable fallback (e.g., showing DB products when YClients is configured) is worse than a clear error. The agent should tell the user "service temporarily unavailable."

4. **Rate limiting:** Responsibility of `BaseIntegrationClient` in the provider package, not the CRM platform. Each client knows its own API limits.

5. **Multiple integrations per company:** Supported. A company can have one provider for scheduling + another for CRM. `_resolve()` iterates all enabled integrations and collects matches for the requested service class. Exactly zero (fallback to base) or one match expected; multiple matches raise `IntegrationConflictError`. `get_by_capability()` is used separately by capability action endpoints to find the right integration for a specific capability.

---

## Rollback Strategy

- **Phase 1:** Pure additions to common lib. Remove new file to rollback.
- **Phase 2:** Standalone encryption service. Remove `crypto.py` and env var to rollback.
- **Phase 3:** New module with no dependents until Phase 4+. Delete module + revert migration.
- **Phase 4:** Self-contained provider packages. Delete a package to remove that integration entirely.
- **Phase 5:** AgentContextAssembler changes are additive. Revert dependency to singleton `CompaniesService` to disable integration resolution.
- **Phase 6:** Scaffolding only. Capability routes and tool handler patterns are empty shells. Remove the empty modules to rollback.
