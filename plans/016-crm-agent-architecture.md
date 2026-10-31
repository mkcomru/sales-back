# Plan 016: CRM-Agent Architecture

## Objective

Design and implement a separate AI-powered agent service that enables managers to interact with CRM data through a conversational UI sidebar. The agent must capture all aspects of CRM operations: reading threads/customers, creating notes, filtering records, analyzing data, and performing targeted updates.

**Critical constraint**: AI API calls cannot be located in the Backend service. They must run in a separate container deployed in a safe zone (outside restricted regions). This means:
- Backend service can be deployed anywhere (including restricted regions)
- Sales-Agent and CRM-Agent must be deployed in safe zones (outside restricted regions)
- All LLM API calls originate from safe zone services
- Backend communicates with AI services via HTTP, but never makes LLM calls itself

---

## Context: Why a Separate Service

### The Problem with Extending Sales-Agent

Sales-Agent exists and works well for its purpose: processing external customer messages through an LLM pipeline and generating responses. However, the CRM-Agent use case is fundamentally different:

| Dimension | Sales-Agent | CRM-Agent |
|-----------|-------------|-----------|
| Trigger | External customer message | Manager query in UI sidebar |
| Context scope | Single conversation thread | Entire CRM (cross-customer, cross-thread) |
| Output | Reply sent to customer | Answer/action for manager |
| Latency model | Async with debounce window (45s) | Interactive, real-time streaming |
| Authentication | Service-to-service (machine identity) | Manager JWT (user identity matters for permissions) |
| Tools | Customer-focused (set_fields, handoff) | CRM-wide (list, filter, aggregate, create notes) |
| Failure impact | Customer doesn't receive reply | Manager can't query data |

### Decision: Option B - Separate CRM-Agent Service

**Rationale:**

1. **Resource contention**: Customer message processing has batch windows and can spike. Manager queries need immediate response. These shouldn't compete for resources.

2. **Different scaling profiles**: Sales-Agent scales by message volume. CRM-Agent scales by concurrent managers. These don't correlate.

3. **Authentication boundary**: Sales-Agent uses `X-Service-Key` (machine identity). CRM-Agent needs to know which manager is asking to enforce permissions. Mixing auth models in one service creates security complexity.

4. **Independent evolution**: Customer AI evolves based on conversion metrics. CRM AI evolves based on manager productivity. Coupling them slows both.

5. **The safe zone constraint is satisfied either way**: Both services must run in a safe zone (outside restricted regions). The constraint is "not in Backend", not "must be single service".

---

## Architecture Overview

### Service Topology

```
┌─────────────────────────────────────────────────────────────────┐
│                        Frontend                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  CRM UI                    │  Sidebar Chat Component    │    │
│  │  - Thread list             │  - Message input           │    │
│  │  - Customer profiles       │  - Streaming response      │    │
│  │  - Dashboard               │  - Action confirmations    │    │
│  └─────────────────────────────────────────────────────────┘    │
└────────────────────────────────┬────────────────────────────────┘
                                 │
                    WebSocket + REST (JWT auth)
                                 │
┌────────────────────────────────▼────────────────────────────────┐
│                              Backend                             │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Existing CRM Core         │  New: Agent Proxy Layer    │    │
│  │  - Auth, Companies         │  - Session management      │    │
│  │  - Threads, Messages       │  - Manager context relay   │    │
│  │  - Products, Categories    │  - Response streaming      │    │
│  └─────────────────────────────────────────────────────────┘    │
└────────────────────────────────┬────────────────────────────────┘
                                 │
                    HTTP (Service Key + Manager Context)
                                 │
┌────────────────────────────────▼────────────────────────────────┐
│                         Safe Zone                                │
│                    (AI Processing Zone)                          │
│  ┌────────────────────┐       ┌────────────────────────────┐    │
│  │    sales-agent     │       │        crm-agent           │    │
│  │  ────────────────  │       │  ────────────────────────  │    │
│  │  Customer Flows    │       │  Manager Flows             │    │
│  │  External Messages │       │  UI Sidebar Queries        │    │
│  │  Debounced         │       │  Streaming Responses       │    │
│  └────────────────────┘       └────────────────────────────┘    │
│             │                             │                      │
│             └──────────┬──────────────────┘                      │
│                        │                                         │
│               ┌────────▼────────┐                                │
│               │   libs/ai-core   │                               │
│               │  ───────────────│                                │
│               │  LLMClient      │                                │
│               │  ToolLoop       │                                │
│               │  Telemetry      │                                │
│               └─────────────────┘                                │
└─────────────────────────────────────────────────────────────────┘
```

### Key Architectural Decisions

**1. Backend as Proxy**

Frontend never talks directly to CRM-Agent. Backend acts as:
- Authentication gateway (validates manager JWT)
- Context provider (extracts manager identity, company, permissions)
- Session storage (maintains conversation history)
- Streaming relay (forwards agent responses to frontend)

This keeps CRM-Agent stateless and focused on AI processing.

**2. CRM-Agent Has No Direct Database Access**

CRM-Agent executes tools by calling Backend internal APIs. This:
- Maintains single source of truth for data access patterns
- Leverages existing authorization logic in Backend
- Keeps audit trail in one place
- Allows Backend to evolve data layer independently

**3. Shared AI Infrastructure**

Common LLM client, tool loop, and telemetry live in `libs/ai-core`. Both Sales-Agent and CRM-Agent import from this library. Benefits:
- No code duplication
- Consistent LLM interaction patterns
- Single place to update provider integrations
- Shared observability setup

**4. Tool-Based Architecture**

CRM-Agent capabilities are defined as discrete tools. Each tool:
- Has a clear single responsibility
- Declares required permissions
- Executes via Backend API call
- Returns structured result for LLM consumption

This makes capabilities:
- Easy to add incrementally
- Testable in isolation
- Permission-controllable
- Auditable

---

## Communication Patterns

### Flow: Manager Query → Response

1. Manager types query in sidebar
2. Frontend sends to Backend with JWT
3. Backend validates JWT, extracts manager context (id, company, role, permissions)
4. Backend loads or creates session (conversation history)
5. Backend forwards query + context to CRM-Agent
6. CRM-Agent sends to LLM with tools available
7. LLM may call tools; CRM-Agent executes via Backend APIs
8. LLM generates final response
9. CRM-Agent streams response to Backend
10. Backend relays stream to Frontend
11. Backend saves response to session history

### Authentication Model

**Frontend → Backend**: Standard JWT (same as CRM UI)

**Backend → CRM-Agent**: Service-to-service key + manager context header
- `X-Service-Key`: Shared secret for internal services
- `X-Manager-Id`: Manager performing the query
- `X-Company-Id`: Company scope
- `X-Permissions`: Allowed operations

**CRM-Agent → Backend** (tool execution): Service-to-service key + on-behalf-of
- `X-Service-Key`: Same shared secret
- `X-On-Behalf-Of`: `manager:{id}` for audit trail

### Session Management

Sessions maintain conversation context across queries. Stored in Backend (not CRM-Agent):
- Session ID (UUID)
- Manager ID
- Company ID
- Created timestamp
- Message history (user queries + agent responses)
- Optional: last tool calls, cited data

CRM-Agent is stateless. It receives full context with each request and returns response. Backend handles persistence.

---

## Tool Philosophy

### Categories of Tools

**Read Operations** (safe, high-value for MVP):
- List and filter entities (threads, customers)
- Get detailed views (thread with messages, customer profile)
- Search across data (full-text message search)
- Analytics and aggregations (conversion funnel, volume stats)

**Write Operations** (targeted, single-item):
- Create notes on threads
- Update single thread stage
- Assign thread to manager
- Update customer fields

**Bulk Operations** (powerful, requires confirmation):
- Bulk stage updates
- Bulk assignments
- Batch exports

**Dangerous Operations** (Phase 2+, explicit confirmation):
- Customer rejection
- Thread closure
- Data deletion

### MVP Tool Set

Focus on read-heavy, safe operations that prove value:

1. `list_threads` - Filter by stage, state, channel, date, assignee
2. `get_thread` - Single thread with message history
3. `get_customer` - Customer profile with quiz answers and thread list
4. `search_messages` - Full-text search across messages
5. `get_analytics` - Conversion funnel, volume statistics
6. `create_note` - Add internal note to thread
7. `update_stage` - Change single thread stage
8. `assign_thread` - Assign thread to manager

Eight tools cover 80% of "tell me about my CRM" use cases without dangerous operations.

### Permission Model

Each tool declares required permissions. CRM-Agent checks before execution:

```
list_threads     → read_threads
get_customer     → read_customers
create_note      → write_notes
update_stage     → write_threads
bulk_update      → write_threads + bulk_operations
```

Permissions come from manager context (role-based in Backend). CRM-Agent trusts but verifies.

---

## Streaming and Real-Time

### Why Streaming Matters

CRM queries can take 5-15 seconds (LLM thinking + tool calls). Without streaming:
- Manager stares at blank screen
- No indication of progress
- Poor UX for interactive tool

With streaming:
- Manager sees agent "thinking" indicators
- Tool calls appear as they happen
- Response text appears progressively
- Feels responsive even when slow

### Stream Event Types

```
thinking     → Agent is processing
tool_call    → About to execute tool (name, arguments)
tool_result  → Tool returned data (summary, not full payload)
text         → Response text chunk
done         → Query complete
error        → Something failed
```

### Implementation Options

**Option A: SSE through Backend** (recommended for MVP)
- Backend opens SSE connection to frontend
- Backend makes HTTP request to CRM-Agent
- CRM-Agent returns chunked/streaming response
- Backend relays chunks as SSE events

**Option B: WebSocket through Backend**
- Reuse existing WebSocket infrastructure
- More complex routing logic
- Better for bidirectional (future: agent asks clarifying questions)

**Option C: Direct CRM-Agent WebSocket**
- Lowest latency
- Duplicates auth logic
- Complicates deployment (need public endpoint for safe zone service)

Start with Option A, consider B for production.

---

## What Changes in Backend

### New Responsibilities

1. **Agent Proxy Endpoint**: Receive manager queries, forward to CRM-Agent, relay responses
2. **Session Storage**: Store agent conversation history per manager
3. **Internal APIs for Tools**: Endpoints CRM-Agent calls to execute tools (some exist, some new)
4. **Manager Context Resolution**: Extract permissions from JWT/role

### New Internal Endpoints (for CRM-Agent tool calls)

Most data access already exists in Backend. Need thin internal routes:
- Thread listing with extended filters
- Message full-text search
- Analytics aggregations
- Note creation with author attribution

These are internal (`/api/v1/internal/...`) and service-key protected.

### What Doesn't Change

- Existing CRM UI APIs
- Sales-Agent communication
- Transport module integration
- Database schema (maybe add sessions table)

---

## What's Extracted to libs/ai-core

### From Sales-Agent

- `LLMClient` - OpenAI-compatible client with provider abstraction
- `ToolLoop` - Tool calling loop with retry and tracing
- `ToolSpec` - Tool definition structure
- `ToolRegistry` - Tool registration and lookup
- `Tracer` - Langfuse integration for observability

### Principles

- Zero business logic in ai-core
- Pure infrastructure: "call LLM", "run tool", "trace span"
- Both services import and configure for their use case
- Provider changes (new LLM, new tracing) happen once

---

## MVP Scope

### In Scope (Phase 1)

- Separate CRM-Agent service with production-ready architecture
- libs/ai-core extraction from Sales-Agent
- 8 read-heavy and safe-write tools
- Backend proxy with session management
- Basic streaming (SSE)
- Permission checking
- Structured logging and Langfuse tracing

### Out of Scope (Phase 2+)

- Bulk operations
- Dangerous operations (delete, reject)
- Multi-turn confirmations ("Are you sure?")
- Proactive suggestions ("You have stale leads")
- Automated actions (auto-assign rules)
- Rich media in responses (charts, tables rendered by agent)

### Success Criteria

1. Manager can ask "Show me threads stuck in qualification for more than 3 days" and get accurate answer
2. Manager can ask "Add a note to thread X saying follow up needed" and see note created
3. Response streams to UI within 500ms of first LLM token
4. Tool execution respects manager permissions
5. Conversation context maintained across queries in same session

---

## Complexity Assessment

### Effort Estimate

| Component | Days | Risk |
|-----------|------|------|
| libs/ai-core extraction | 2-3 | Low (refactoring) |
| CRM-Agent service skeleton | 1 | Low (boilerplate) |
| CRM-Agent pipeline | 2-3 | Medium (new code) |
| Read tools (5) | 3-4 | Low |
| Write tools (3) | 2 | Low |
| Backend internal endpoints | 2-3 | Low |
| Backend proxy + sessions | 2-3 | Medium |
| System prompt tuning | 1-2 | Low but critical |
| Integration testing | 2-3 | Medium |

**Total: 3-4 weeks** for one focused senior developer, or 2 weeks with two people in parallel.

### Risk Mitigation

**Low risk factors:**
- Architecture extends existing patterns
- No new external dependencies
- Read-only operations can't corrupt data
- Backend has most data access logic already

**Medium risk factors:**
- Streaming relay is new pattern (may need iteration)
- LLM tool calling quality depends on prompt (needs tuning)
- Session management is new feature (edge cases)

**Mitigated by MVP scope:**
- No bulk operations = no mass data changes
- No automated actions = human always in control
- Read-heavy = safe to experiment and iterate

---

## Recommended Approach

### Week 1: Vertical Slice

Prove the architecture with minimal scope:
- Extract libs/ai-core
- CRM-Agent with 3 tools: `list_threads`, `get_thread`, `create_note`
- Backend proxy without streaming (request-response)
- Test via CLI or Postman

This validates:
- Service communication works
- LLM understands CRM queries
- Tools execute correctly
- Architecture is sound

### Weeks 2-3: Full MVP

Expand from validated slice:
- Add remaining 5 tools
- Implement streaming
- Session management
- Permission checking
- Frontend integration support

### Week 4: Polish

- Error handling edge cases
- Prompt refinement based on testing
- Performance optimization
- Documentation

---

## Open Questions

1. **Frontend ownership**: Who builds the sidebar component? What framework/patterns?

2. **Session lifetime**: How long do sessions persist? Auto-cleanup after inactivity?

3. **Rate limiting**: Should CRM-Agent queries be rate-limited per manager?

4. **Analytics tools scope**: What specific metrics are highest priority?

5. **Multi-company managers**: Can a manager query across companies they have access to?

---

## Appendix: Example Interactions

**Query**: "How many new threads came in last week from Telegram?"

**Agent thinking**: Need to count threads by channel and date range.

**Tool call**: `get_analytics(metric="daily_volume", date_from="2026-01-04", date_to="2026-01-11", group_by="channel")`

**Response**: "Last week you received 47 new threads from Telegram, compared to 23 from WhatsApp and 12 from Bitrix."

---

**Query**: "Show me customers who answered 'yes' to the budget question but haven't been contacted in a week"

**Agent thinking**: Need to filter by quiz answers and thread activity.

**Tool call**: `list_threads(inactive_days=7)` + filter by quiz_answers in response

**Response**: "Found 8 customers matching your criteria: [list with names and last contact dates]"

---

**Query**: "Add a note to Maria's thread saying she needs a callback tomorrow"

**Agent thinking**: Need to find Maria's thread, then create note.

**Tool call**: `list_threads(search="Maria")` → finds thread_id

**Tool call**: `create_note(thread_id="abc123", content="Needs callback tomorrow")`

**Response**: "Done. Added note to Maria Ivanova's thread (last active 2 days ago in qualification stage)."
