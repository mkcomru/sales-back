# Architecture Diagrams

Visual representations of system architecture and message flows.

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         External Systems                         │
├──────────────┬──────────────┬─────────────────────┤
│ Telegram API │  Wappi Hub   │  Custom Connectors │
└──────┬───────┴──────┬───────┴─────────┬─────────┘
       │              │                 │
       │              │                 │
┌──────▼──────────────▼─────────────────▼─────────┐
│                    Transport Layer                              │
├──────────────────┬──────────────────────────────┤
│ Telegram Module  │  Wappi Module               │
│  (Polling/       │  (Webhooks)      │
│   Webhooks)      │                  │
└──────┬───────────┴──────────┬───────┘
       │                      │                   │
       │                      │
       │              ┌───────▼────────┐
       │              │     Backend     │
       │              │  (Router/API)  │
       │              └───────┬─────────┘
       │                      │
       │                      │
       └──────────────────────┼───────────────────┘
                              │
                              │
                    ┌─────────▼─────────┐
                    │   Sales Agent     │
                    │  (LLM Pipeline)   │
                    └───────────────────┘
                              │
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
┌───────▼────────┐   ┌────────▼────────┐   ┌───────▼────────┐
│  PostgreSQL    │   │      Redis      │   │   Langfuse     │
│  (Schema:      │   │  (Event Streams)│   │  (Telemetry)   │
│   backend)     │   │                 │   │                │
└────────────────┘   └─────────────────┘   └────────────────┘
```

## Message Flow: Unified Pattern (Telegram/Wappi)

```
┌─────────────┐
│   Telegram  │
│     API     │
└──────┬──────┘
       │
       │ Update received
       │
┌──────▼──────────────────────────────────────────────┐
│         Telegram Module                             │
│  - Receives update from Telegram API               │
│  - Normalizes to InboundEnvelope                  │
│  - Validates connector via Backend                 │
└──────┬─────────────────────────────────────────────┘
       │
       │ POST /api/v1/messages/inbound
       │ Headers: X-Service-Key, X-Connector-Id
       │
┌──────▼──────────────────────────────────────────────┐
│              Backend                                 │
│  - Validates connector                              │
│  - Saves message to DB                              │
│  - Checks if assistant_active                       │
│  - Forwards to Sales Agent if active                │
└──────┬─────────────────────────────────────────────┘
       │
       │ POST /api/v1/internal/messages/inbound
       │ Header: X-Service-Key
       │
┌──────▼──────────────────────────────────────────────┐
│         Sales Agent                                 │
│  - Receives InboundEnvelope                         │
│  - Applies debounce                                 │
│  - Runs LLM pipeline                                │
│  - Generates response                               │
└──────┬─────────────────────────────────────────────┘
       │
       │ POST /api/v1/internal/messages/outbound
       │ Header: X-Service-Key
       │
┌──────▼──────────────────────────────────────────────┐
│              Backend                                 │
│  - Receives OutboundDeliveryRequest                 │
│  - Routes to transport module based on             │
│    connector.type                                   │
└──────┬─────────────────────────────────────────────┘
       │
       │ POST /transport/delivery
       │ Header: X-Service-Key
       │
┌──────▼──────────────────────────────────────────────┐
│         Telegram Module                             │
│  - Receives TransportDeliveryPayload                │
│  - Delivers to Telegram Bot API                     │
└──────┬─────────────────────────────────────────────┘
       │
       │ sendMessage()
       │
┌──────▼──────┐
│   Telegram  │
│     API     │
└─────────────┘
```

## Database Schema Relationships

```
┌─────────────────────────────────────────────────────┐
│              PostgreSQL Database                     │
├─────────────────────────────────────────────────────┤
│                                                      │
│  ┌──────────────────────────────────────────────┐   │
│  │         Schema: backend                      │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐   │   │
│  │  │Company   │──│User      │──│Thread    │   │   │
│  │  └──────────┘  └──────────┘  └──────────┘   │   │
│  │       │            │              │           │   │
│  │       │            │              │           │   │
│  │  ┌────▼────┐  ┌───▼────┐   ┌────▼────┐     │   │
│  │  │Product  │  │Message │   │Customer │     │   │
│  │  └─────────┘  └────────┘   └─────────┘     │   │
│  │                                                │   │
│  │  ┌──────────┐  ┌──────────┐                  │   │
│  │  │Connector │  │Billing   │                  │   │
│  │  └──────────┘  └──────────┘                  │   │
│  └──────────────────────────────────────────────┘   │
│                                                      │
└─────────────────────────────────────────────────────┘
```

## Event Bus Flow

```
┌─────────────────────────────────────────────────────┐
│              Redis Streams                           │
│         Stream: backend.events                       │
├─────────────────────────────────────────────────────┤
│                                                      │
│  ┌──────────────────────────────────────────────┐   │
│  │  Consumer Group: backend                     │   │
│  │  Consumer: backend-instance-1                │   │
│  └──────────────────────────────────────────────┘   │
│                                                      │
│  ┌──────────────────────────────────────────────┐   │
│  │  Consumer Group: sales-agent                 │   │
│  │  Consumer: sales-agent-instance-1             │   │
│  │  Consumer: sales-agent-instance-2            │   │
│  └──────────────────────────────────────────────┘   │
│                                                      │
│  ┌──────────────────────────────────────────────┐   │
│  │  Consumer Group: telegram-module             │   │
│  │  Consumer: telegram-module-instance-1        │   │
│  └──────────────────────────────────────────────┘   │
│                                                      │
└─────────────────────────────────────────────────────┘
```

## Service Dependencies

```
┌─────────────┐
│    Redis    │
└──────┬──────┘
       │
       ├──────────────┐
       │              │
┌──────▼──────┐  ┌────▼─────┐
│   Backend   │  │PostgreSQL│
└──────┬──────┘  └──────────┘
       │
       ├──────────────┬──────────────┐
       │              │              │
┌──────▼──────┐  ┌────▼──────┐  ┌────▼──────┐
│Sales Agent  │  │Telegram   │  │  Wappi    │
└─────────────┘  │  Module   │  │  Module   │
                 └───────────┘  └───────────┘
```

## Connector Configuration Flow

```
┌─────────────────────────────────────────────────────┐
│              Backend API                             │
│  POST /api/v1/transport/connectors                 │
└──────┬──────────────────────────────────────────────┘
       │
       │ Connector created/updated
       │
┌──────▼──────────────────────────────────────────────┐
│         PostgreSQL (backend schema)                 │
│  Connector record stored                            │
└──────┬─────────────────────────────────────────────┘
       │
       │ Event: connector.updated
       │ (if eventing enabled)
       │
┌──────▼──────────────────────────────────────────────┐
│         Redis Streams                               │
│  backend.events stream                              │
└──────┬─────────────────────────────────────────────┘
       │
       │ Consumed by Sales Agent
       │
┌──────▼──────────────────────────────────────────────┐
│         Sales Agent                                 │
│  ConnectorSync background task                     │
│  - Polls Backend periodically                      │
│  - Updates runtime connectors dict                 │
└─────────────────────────────────────────────────────┘
```

## Authentication Flow

```
┌─────────────────────────────────────────────────────┐
│         Managed Connector                           │
│  (Telegram Module, Wappi Module)                   │
└──────┬──────────────────────────────────────────────┘
       │
       │ Request with:
       │ X-Service-Key: <SERVICE__API_KEY>
       │ X-Connector-Id: <connector_id>
       │
┌──────▼──────────────────────────────────────────────┐
│              Backend                                 │
│  - Validates X-Service-Key                          │
│  - Looks up connector by connector_id               │
│  - Returns ConnectorContext                         │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│         Custom Connector                            │
│  (External system)                                  │
└──────┬──────────────────────────────────────────────┘
       │
       │ Request with:
       │ Authorization: Bearer sk_xxx
       │
┌──────▼──────────────────────────────────────────────┐
│              Backend                                 │
│  - Validates Bearer token                          │
│  - Looks up ConnectorApiKey                         │
│  - Returns ConnectorContext                         │
└─────────────────────────────────────────────────────┘
```
