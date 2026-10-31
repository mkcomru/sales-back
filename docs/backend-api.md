# Backend API Reference

Backend exposes REST API at `/api/v1/*` for platform configuration and message routing.

## Base URL

All endpoints are prefixed with `/api/v1`.

## Authentication

### Service-to-Service Authentication

For internal service communication (transport modules, sales-agent):

```
X-Service-Key: <SERVICE__API_KEY>
X-Connector-Id: <connector_id>  # For managed connectors
```

### User Authentication

For user-facing endpoints:

```
Authorization: Bearer <access_token>
```

JWT tokens obtained via `/api/v1/auth/login` or `/api/v1/auth/refresh`.

### Custom Connector Authentication

For custom connectors:

```
Authorization: Bearer sk_xxx
```

API keys managed via `/api/v1/transport/connectors/{id}/api-keys`.

## Endpoint Groups

### Message Routing

**Public Endpoints:**

- `POST /api/v1/messages/inbound` - Receive inbound messages from transport modules
  - Auth: `X-Service-Key` + `X-Connector-Id` (managed) or `Authorization: Bearer` (custom)
  - Validates connector, saves to DB, forwards to Sales Agent if assistant active

**Internal Endpoints:**

- `POST /api/v1/internal/messages/outbound` - Receive outbound messages from Sales Agent
  - Auth: `X-Service-Key` (service-to-service)
  - Routes to appropriate transport module based on `connector.type`

### Transport Connectors

**Base Path:** `/api/v1/transport/connectors`

- `GET /api/v1/transport/connectors` - List connectors (filters: `?type=telegram&enabled=true`)
- `POST /api/v1/transport/connectors` - Create connector
- `GET /api/v1/transport/connectors/{connector_db_id}` - Get connector by DB ID
- `PATCH /api/v1/transport/connectors/{connector_db_id}` - Update connector
- `DELETE /api/v1/transport/connectors/{connector_db_id}` - Delete connector
- `POST /api/v1/transport/connectors/{connector_db_id}/api-keys` - Create API key for custom connector
- `GET /api/v1/transport/connectors/{connector_db_id}/api-keys` - List API keys
- `DELETE /api/v1/transport/connectors/{connector_db_id}/api-keys/{key_id}` - Delete API key
- `POST /api/v1/transport/connectors/{connector_id}/sync/start` - Start history sync
- `GET /api/v1/transport/connectors/{connector_id}/sync/status` - Get sync status
- `POST /api/v1/transport/connectors/{connector_id}/sync/cancel` - Cancel sync

### Companies

**Base Path:** `/api/v1/companies`

- `GET /api/v1/companies` - List companies (user's companies or all if superuser)
- `POST /api/v1/companies` - Create company (superuser only)
- `GET /api/v1/companies/{company_id}` - Get company details
- `PATCH /api/v1/companies/{company_id}` - Update company
- `DELETE /api/v1/companies/{company_id}` - Delete company
- `GET /api/v1/companies/{company_id}/managers` - List company members
- `GET /api/v1/companies/{company_id}/config` - Get company configuration
- `GET /api/v1/companies/{company_id}/faqs` - List FAQs (paginated)
- `POST /api/v1/companies/{company_id}/faqs` - Create FAQ

**Internal:**

- `GET /api/v1/internal/companies/{company_id}/specification` - Get complete company specification for Sales Agent

### Chat & Threads

**Base Path:** `/api/v1/companies/{company_id}`

- `GET /api/v1/companies/{company_id}/threads` - List threads (paginated, filters: channel_type, state, assignee)
- `GET /api/v1/companies/{company_id}/threads/{thread_id}` - Get thread details
- `POST /api/v1/companies/{company_id}/threads` - Create thread
- `PATCH /api/v1/companies/{company_id}/threads/{thread_id}` - Update thread
- `GET /api/v1/companies/{company_id}/threads/{thread_id}/messages` - Get thread messages
- `POST /api/v1/companies/{company_id}/threads/{thread_id}/messages` - Create message
- `PATCH /api/v1/companies/{company_id}/threads/{thread_id}/messages/{message_id}` - Update message
- `PATCH /api/v1/companies/{company_id}/threads/{thread_id}/assignee` - Assign thread
- `PATCH /api/v1/companies/{company_id}/threads/{thread_id}/stage` - Update thread stage
- `PATCH /api/v1/companies/{company_id}/threads/{thread_id}/state` - Update thread state
- `PUT /api/v1/companies/{company_id}/threads/{thread_id}/custom-fields` - Update custom fields

**WebSocket:**

- `WS /api/v1/chat/ws` - Real-time updates for chat threads

**Internal:**

- `POST /api/v1/internal/chat/messages/ingest` - Ingest message from Sales Agent
- `PATCH /api/v1/internal/chat/threads/{thread_id}/assistant-active` - Update assistant active status
- `POST /api/v1/internal/chat/threads/{thread_id}/langfuse-session` - Create Langfuse session

### Customers

**Base Path:** `/api/v1/companies/{company_id}`

- `GET /api/v1/companies/{company_id}/customers` - List customers
- `GET /api/v1/companies/{company_id}/customers/{customer_id}` - Get customer details
- `POST /api/v1/companies/{company_id}/customers` - Create or get customer
- `PATCH /api/v1/companies/{company_id}/customers/{customer_id}` - Update customer
- `PATCH /api/v1/companies/{company_id}/customers/{customer_id}/fields` - Update customer fields
- `PATCH /api/v1/companies/{company_id}/customers/{customer_id}/quiz-answers` - Update quiz answers
- `PATCH /api/v1/companies/{company_id}/customers/{customer_id}/notes` - Update notes
- `POST /api/v1/companies/{company_id}/customers/{customer_id}/reject` - Reject customer

### Billing

**Base Path:** `/api/v1/companies/{company_id}/billing`

- `POST /api/v1/companies/{company_id}/billing/top-up` - Top up balance (admin only)
- `GET /api/v1/companies/{company_id}/billing/balance` - Get balance
- `GET /api/v1/companies/{company_id}/billing/ledger` - Get ledger entries (paginated, filters: operation_type, dates, order_id)

### Products

**Base Path:** `/api/v1/companies/{company_id}`

- `GET /api/v1/companies/{company_id}/products` - List company products

**Internal:**

- `POST /api/v1/products/` - Create product
- `GET /api/v1/products/` - List all products
- `GET /api/v1/products/{product_id}` - Get product
- `PATCH /api/v1/products/{product_id}` - Update product
- `DELETE /api/v1/products/{product_id}` - Delete product

### Categories

**Base Path:** `/api/v1/categories`

- `GET /api/v1/categories` - List categories
- `POST /api/v1/categories` - Create category
- `GET /api/v1/categories/{category_id}` - Get category
- `PATCH /api/v1/categories/{category_id}` - Update category
- `DELETE /api/v1/categories/{category_id}` - Delete category

### Forms & Fields

**Base Path:** `/api/v1/companies/{company_id}/fields`

- `GET /api/v1/companies/{company_id}/fields` - List fields
- `POST /api/v1/companies/{company_id}/fields` - Create field
- `GET /api/v1/companies/{company_id}/fields/{field_id}` - Get field
- `PATCH /api/v1/companies/{company_id}/fields/{field_id}` - Update field
- `DELETE /api/v1/companies/{company_id}/fields/{field_id}` - Delete field
- `POST /api/v1/companies/{company_id}/fields/{field_id}/options` - Add field option
- `DELETE /api/v1/companies/{company_id}/fields/{field_id}/options/{option_id}` - Delete field option

### Prompts

**Base Path:** `/api/v1/prompts`

- `GET /api/v1/prompts` - List prompts
- `POST /api/v1/prompts` - Create prompt
- `GET /api/v1/prompts/{prompt_id}` - Get prompt
- `PATCH /api/v1/prompts/{prompt_id}` - Update prompt
- `DELETE /api/v1/prompts/{prompt_id}` - Delete prompt

### Tools

**Base Path:** `/api/v1/tools`

- `GET /api/v1/tools` - List tools
- `POST /api/v1/tools` - Create tool
- `GET /api/v1/tools/{tool_id}` - Get tool
- `PATCH /api/v1/tools/{tool_id}` - Update tool
- `DELETE /api/v1/tools/{tool_id}` - Delete tool

### Users

**Base Path:** `/api/v1/users`

- `GET /api/v1/users` - List users
- `GET /api/v1/users/{user_id}` - Get user
- `PATCH /api/v1/users/{user_id}` - Update user
- `DELETE /api/v1/users/{user_id}` - Delete user

### Auth

**Base Path:** `/api/v1/auth`

- `POST /api/v1/auth/login` - Login (get access + refresh tokens)
- `POST /api/v1/auth/refresh` - Refresh access token
- `POST /api/v1/auth/logout` - Logout (revoke refresh token)
- `POST /api/v1/auth/logout-all` - Logout from all devices
- `POST /api/v1/auth/signup` - Create user (superuser only)

### Sync

**Base Path:** `/api/v1/sync`

- `POST /api/v1/sync/batch` - Process sync batch
- `POST /api/v1/sync/status` - Update sync status
- `POST /api/v1/sync/heartbeat` - Send sync heartbeat
- `GET /api/v1/sync/cursor/{connector_id}` - Get sync cursor

### Simulator

**Base Path:** `/api/v1/simulator`

- `POST /api/v1/simulator/sessions` - Create simulator session
- `GET /api/v1/simulator/sessions/{session_id}` - Get session

## Error Responses

All errors follow standard HTTP status codes:

- `400 Bad Request` - Invalid request data
- `401 Unauthorized` - Missing or invalid authentication
- `403 Forbidden` - Insufficient permissions
- `404 Not Found` - Resource not found
- `422 Unprocessable Entity` - Validation error
- `500 Internal Server Error` - Server error

Error response format:

```json
{
  "detail": "Error message or object"
}
```

For validation errors:

```json
{
  "detail": [
    {
      "loc": ["body", "field_name"],
      "msg": "Error message",
      "type": "error_type"
    }
  ]
}
```

## Pagination

Paginated endpoints accept query parameters:

- `limit` - Page size (default: 50, max: 100)
- `offset` - Page offset (default: 0)

Response format:

```json
{
  "items": [...],
  "total": 100,
  "limit": 50,
  "offset": 0
}
```

## Health Check

- `GET /health` - Returns `200 OK` if service is healthy
