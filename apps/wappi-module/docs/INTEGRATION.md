# Интеграция Wappi Module с Sales Agent

## Архитектура

```
Пользователь → Wappi API
    ↓ webhook
[wappi-module] POST /wappi/{connector_id}/webhook
    ↓ normalize → InboundEnvelope
[backend] POST /api/v1/messages/inbound
    ↓ validate + get ConnectorContext
[backend] POST /api/v1/internal/messages/inbound
    ↓ forward InternalInboundRequest
[sales-agent] POST /api/v1/internal/messages/inbound
    ↓ normalize → debounce → pipeline
[sales-agent] AgentsPipelineResult
    ↓ OutboundDeliveryRequest
[sales-agent] POST /api/v1/internal/messages/outbound
    ↓ route by connector.type
[backend] TransportClient → POST /transport/delivery
    ↓ validate + idempotency
[wappi-module] TransportDeliveryService
    ↓ WappiApiClient
Wappi API → Пользователь
```

## Настройка в Backend

### 1. Создать Wappi Connector в БД

```bash
POST http://backend:8080/transport/wappi/connectors
X-Service-Key: your-service-key
Content-Type: application/json

{
  "connector_id": "wappi-company1",
  "company_id": 1,
  "channel_type": "telegram_user_proxy",
  "wappi_token": "WAPPI_API_TOKEN",
  "wappi_profile_id": "PROFILE_ID",
  "transport_endpoint": "http://wappi-module:8002",
  "metadata": {
    "provider": "wappi-hub",
    "api_base_url": "https://wappi.pro"
  },
  "enabled": true
}
```

### 2. Настроить Webhook в Wappi Dashboard

URL: `http://your-domain.com/wappi/{connector_id}/webhook`

Формат входящих сообщений:
```json
{
  "messages": [
    {
      "id": "msg_123",
      "type": "text",
      "body": "текст сообщения",
      "chatId": "79991234567",
      "profile_id": "profile_xyz",
      "senderName": "Иван",
      "time": 1700000000
    }
  ]
}
```

## Переменные окружения

В `.env.shared`:
```bash
BACKEND__URL=http://backend:8080
SERVICE__API_KEY=your-shared-secret-key  # pragma: allowlist secret
```

## Формат отправки в Wappi API

```http
POST https://wappi.pro/api/async/message/send
Authorization: Bearer {wappi_token}
Content-Type: application/json

{
  "profile_id": "PROFILE_ID",
  "recipient": "79991234567",
  "body": "текст сообщения"
}
```

## Тестирование

### 1. Проверка Health Check

```bash
curl http://localhost:8002/healthz
# {"status": "ok"}
```

### 2. Перезагрузка конфигурации

```bash
curl -X POST http://localhost:8002/admin/reload
# {"status": "reloaded"}
```

### 3. Тест Transport Delivery (от Backend)

```bash
curl -X POST http://localhost:8002/transport/delivery \
  -H "Content-Type: application/json" \
  -H "X-Service-Key: your-service-key" \  # pragma: allowlist secret
  -H "X-Connector-Id: wappi-company1" \
  -d '{
    "connector_id": "wappi-company1",
    "company_id": "1",
    "channel_type": "telegram_user_proxy",
    "user_id": "79991234567",
    "conversation_id": "79991234567",
    "correlation_id": "test-123",
    "replies": ["Тестовое сообщение"],
    "metadata": {
      "chat_id": "79991234567"
    }
  }'
```

### 4. Тест Webhook (от Wappi)

```bash
curl -X POST http://localhost:8002/wappi/wappi-company1/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{
      "id": "test_msg",
      "type": "text",
      "body": "Привет!",
      "chatId": "79991234567",
      "profile_id": "profile_xyz",
      "time": 1700000000
    }]
  }'
```

## Логи

Ключевые события:
- `connector.reload.completed` — успешная загрузка конфигурации
- `transport.delivery.delivered` — успешная отправка в Wappi
- `transport.delivery.duplicate` — повторная доставка (идемпотентность)
- `transport.delivery.failed` — ошибка доставки
- `wappi.api.message_sent` — успешный запрос к Wappi API
- `sales_agent.forward.success` — успешный форвард webhook в sales-agent

## Идемпотентность

- TTL кеш по `correlation_id`: 24 часа
- При повторной доставке → `409 Conflict` с `{"status": "duplicate"}`
- Sales Agent автоматически обрабатывает 409 как успех

