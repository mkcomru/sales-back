# 025: WebSocket Frontend Integration

## Objective

Replace polling with WebSocket for real-time updates in the admin panel.

## Current State

- **Backend**: WebSocket endpoint exists at `/companies/{company_id}/threads/{thread_id}/ws`
- **Frontend**: Uses polling (threads every 10s, messages every 5s)

## Tasks

### 1. Create WebSocket hook

- `useWebSocket(threadId: string)` - manages connection lifecycle
- Auto-reconnect with exponential backoff
- Auth via query param (token) since browsers don't support WS headers

### 2. Replace message polling

- Connect to WS when thread is selected
- Handle `message` events to update messages state
- Handle `control` events for thread state changes
- Disconnect when thread is deselected

### 3. Thread list updates (optional)

- Backend currently broadcasts per-thread only
- For thread list updates: either add company-level WS or keep 10s polling

## Notes

- Auth: Backend expects `?token=...` query param (see routers.py:800-836)
- Events: `message`, `control`, `field_update` (see schemas.py)

