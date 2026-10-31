# Wappi Module — API Reference

## Endpoints

### 1. Transport Delivery (исходящие сообщения)

```http
POST /transport/delivery
```

**Назначение:** Принимает сообщения от Sales Agent для отправки через Wappi API.

#### Headers

| Header | Обязательный | Описание |
|--------|--------------|----------|
| `X-Service-Key` | Да | Сервисный ключ (из `SERVICE__API_KEY`) |
| `X-Connector-Id` | Да | ID коннектора |
| `Content-Type` | Да | `application/json` |

#### Request Body

```json
{
  "connector_id": "test",
  "company_id": "1",
  "channel_type": "telegram",
  "user_id": "351311665",
  "conversation_id": "351311665",
  "correlation_id": "sa331c532f",
  "replies": [
    "Привет! Как дела?",
    "Чем могу помочь?"
  ],
  "metadata": {
    "chat_id": "351311665",
    "extra": {
      "platform": "telegram"
    }
  },
  "stage_id": null,
  "handoff": null,
  "delivery_hint": null,
  "attachments": null
}
```

#### Response

**200 OK** — успешная доставка

```json
{
  "status": "delivered",
  "correlation_id": "sa331c532f",
  "delivered_count": 2
}
```

**409 Conflict** — повторная попытка (идемпотентность)

```json
{
  "status": "duplicate",
  "correlation_id": "sa331c532f",
  "detail": "Message already delivered 3600 seconds ago"
}
```

**400 Bad Request** — невалидный payload

```json
{
  "detail": "At least one non-empty reply is required"
}
```

**401 Unauthorized** — неверный service key

```json
{
  "detail": "Invalid service key"
}
```

**404 Not Found** — коннектор не найден

```json
{
  "detail": "Connector 'unknown' not found"
}
```

**500 Internal Server Error** — ошибка при отправке в Wappi API

```json
{
  "detail": "Delivery failed after 3 attempts: Wappi API returned 400"
}
```

#### Логика обработки

```python
1. Валидация X-Service-Key (compare_digest)
2. Валидация X-Connector-Id (существует в ConnectorManager)
3. Парсинг и валидация TransportDeliveryPayload (Pydantic)
4. Проверка идемпотентности (correlation_id в кеше)
   - Если найден → 409 Conflict
   - Если не найден → продолжить
5. Извлечение recipient из metadata.chat_id
6. Для каждого reply в replies:
   - Retry loop (до max_delivery_attempts попыток):
     a. WappiApiClient.send_message()
     b. Если 429/5xx → экспоненциальный backoff и retry
     c. Если 4xx (кроме 429) → прервать с ошибкой
7. Сохранение correlation_id в кеше (TTL 24 часа)
8. Возврат 200 OK
```

#### Пример curl

```bash
curl -X POST http://localhost:8002/transport/delivery \
  -H "Content-Type: application/json" \
  -H "X-Service-Key: your-secret-key" \  # pragma: allowlist secret
  -H "X-Connector-Id: test" \
  -d '{
    "connector_id": "test",
    "company_id": "1",
    "channel_type": "telegram",
    "user_id": "351311665",
    "conversation_id": "351311665",
    "correlation_id": "unique-id-123",
    "replies": ["Тестовое сообщение"],
    "metadata": {
      "chat_id": "351311665"
    }
  }'
```

---

### 2. Wappi Webhook (входящие сообщения)

```http
POST /wappi/{connector_id}/webhook
```

**Назначение:** Принимает webhook-и от Wappi и форвардит их в Sales Agent.

#### Path Parameters

| Параметр | Тип | Описание |
|----------|-----|----------|
| `connector_id` | string | ID коннектора (например, `test`) |

#### Request Body

**Входящее сообщение** (`wh_type: incoming_message`):

```json
{
  "messages": [
    {
      "id": "536022",
      "profile_id": "b51675ef-d41f",
      "wh_type": "incoming_message",
      "timestamp": "2025-11-21T15:01:35+03:00",
      "time": 1763726495,
      "body": "Привет!",
      "type": "text",
      "from": "351311665",
      "to": "902187721",
      "senderName": "Пользователь",
      "chatId": "351311665",
      "platform": "telegram",
      "username": "username",
      "phone": "79990102808"
    }
  ]
}
```

**Статус доставки** (`wh_type: delivery_status`):

```json
{
  "messages": {
    "id": "536024",
    "profile_id": "b51675ef-d41f",
    "wh_type": "delivery_status",
    "timestamp": "2025-11-21T15:02:00+03:00",
    "time": 1763726520,
    "from": "902187721",
    "to": "351311665",
    "chat_id": "351311665",
    "status": "delivered",
    "task_id": "18c16f50c3a9b7949fe1adca8387ead0",
    "platform": "telegram"
  }
}
```

> **Важно:** Для `incoming_message` — массив, для `delivery_status` — объект!

#### Response

**202 Accepted** — успешный форвард в Sales Agent

```json
{
  "status": "accepted"
}
```

**404 Not Found** — коннектор не найден

```json
{
  "detail": "Unknown connector 'unknown'. Available: ['test']"
}
```

**400 Bad Request** — невалидный JSON

```json
{
  "detail": "Invalid JSON payload"
}
```

**502 Bad Gateway** — Sales Agent недоступен

```json
{
  "detail": "Failed to forward webhook to Sales Agent"
}
```

#### Логика обработки

```python
1. Парсинг JSON payload из request.body
2. Логирование: wappi.webhook.received
3. Получение connector из ConnectorManager
   - Если не найден → 404 с доступными connector_id
4. BackendInboundClient.forward_update():
   - Нормализует сообщения в InboundEnvelope формат
   - POST http://backend:8001/api/v1/messages/inbound
   - Headers: X-Service-Key, X-Connector-Id
   - Body: InboundEnvelope (нормализованный формат)
5. Обработка ответа:
   - 200/202 → 202 Accepted
   - Другие коды → 502 Bad Gateway
6. Логирование: wappi.webhook.forwarded / wappi.webhook.forward_failed
```

#### Пример curl

```bash
curl -X POST http://localhost:8002/wappi/test/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{
      "id": "msg123",
      "wh_type": "incoming_message",
      "body": "Привет!",
      "chatId": "351311665",
      "profile_id": "b51675ef-d41f",
      "type": "text",
      "platform": "telegram"
    }]
  }'
```

---

### 3. Admin: Force Reload

```http
POST /admin/reload
```

**Назначение:** Принудительная перезагрузка конфигурации коннекторов из backend.

#### Request

Без параметров.

#### Response

**200 OK** — успешная перезагрузка

```json
{
  "status": "reloaded",
  "connectors_count": 1
}
```

**500 Internal Server Error** — ошибка при загрузке из backend

```json
{
  "detail": "Failed to reload connectors: Connection refused"
}
```

#### Логика обработки

```python
1. ConnectorManager.reload()
2. Загрузка конфигурации из backend
3. Diff анализ и обновление _connectors
4. Возврат количества загруженных коннекторов
```

#### Пример curl

```bash
curl -X POST http://localhost:8002/admin/reload
```

---

### 4. Health Check

```http
GET /healthz
```

**Назначение:** Проверка доступности сервиса (для load balancer / k8s liveness probe).

#### Request

Без параметров.

#### Response

**200 OK**

```json
{
  "status": "ok"
}
```

#### Пример curl

```bash
curl http://localhost:8002/healthz
```

---

## Swagger UI

Доступен по адресу: `http://localhost:8002/docs`

### Особенности:

- **Для `/transport/delivery`**: Swagger покажет форму для X-Service-Key и X-Connector-Id
- **Для `/wappi/{connector_id}/webhook`**: Используется `Request` объект, поэтому Swagger **не покажет** форму для тела запроса (это ожидаемое поведение)

### Тестирование через Swagger:

1. Откройте `http://localhost:8002/docs`
2. Найдите `POST /transport/delivery`
3. Нажмите "Try it out"
4. Заполните headers: `X-Service-Key`, `X-Connector-Id`
5. Вставьте JSON body
6. Нажмите "Execute"

---

## Wappi API Integration

### Отправка сообщения (используется wappi-module)

```http
POST https://wappi.pro/tapi/async/message/send?profile_id={profile_id}
Authorization: {wappi_token}
Content-Type: application/json

{
  "body": "текст сообщения",
  "recipient": "351311665"
}
```

**Важно:**
- `profile_id` передаётся как **query parameter**, НЕ в теле!
- `Authorization` header содержит **только токен**, без префикса "Bearer"
- `recipient` — это `chatId` из входящего webhook

### Пример успешного ответа

```json
{
  "status": "done",
  "timestamp": 1763726517,
  "time": "2025-11-21T15:01:57+03:00",
  "detail": "Message sent to queue",
  "task_id": "18c16f50c3a9b7949fe1adca8387ead0"
}
```

### Пример ошибки (400 Bad Request)

```json
{
  "status": "error",
  "detail": "profile_id incorrect"
}
```

**Причины:**
- Короткий `profile_id` вместо полного UUID
- Неверный токен
- Неверный `recipient`

---

## Sequence Diagrams

### Исходящее сообщение (Sales Agent → Wappi)

```
Sales Agent            wappi-module          Wappi API
    |                       |                     |
    |--- POST /transport/---|                     |
    |    delivery           |                     |
    |                       |                     |
    |              validate headers               |
    |              check correlation_id           |
    |              extract recipient              |
    |                       |                     |
    |                       |--- POST /tapi/------|
    |                       |    async/message    |
    |                       |    send             |
    |                       |                     |
    |                       |<--- 200 OK ---------|
    |                       |    {task_id}        |
    |                       |                     |
    |                  save to cache              |
    |<--- 200 OK ----------|                     |
    |    {delivered}        |                     |
```

### Входящее сообщение (Wappi → Sales Agent)

```
Wappi API              wappi-module         Sales Agent
    |                       |                     |
    |--- POST /wappi/------|                     |
    |    {connector_id}/    |                     |
    |    webhook            |                     |
    |                       |                     |
    |              log payload                    |
    |              get connector                  |
    |                       |                     |
    |                       |--- POST /{id}/-----|
    |                       |    webhook          |
    |                       |                     |
    |                       |                normalize
    |                       |                debounce
    |                       |                pipeline
    |                       |                     |
    |                       |<--- 200 OK ---------|
    |<--- 202 Accepted ----|                     |
    |                       |                     |
    |                       |                     |--- POST /transport/
    |                       |                     |    delivery
    |                       |<--------------------|
    |                       |                     |
    |              (цикл повторяется)             |
```

---

## Error Handling

### HTTP Status Codes

| Код | Значение | Причина |
|-----|----------|---------|
| 200 | OK | Успешная обработка |
| 202 | Accepted | Webhook принят |
| 400 | Bad Request | Невалидный payload |
| 401 | Unauthorized | Неверный service key |
| 404 | Not Found | Коннектор не найден |
| 409 | Conflict | Повторная доставка (идемпотентность) |
| 422 | Unprocessable Entity | Validation error (Pydantic) |
| 500 | Internal Server Error | Внутренняя ошибка |
| 502 | Bad Gateway | Внешний сервис недоступен |

### Retry Logic (Transport Delivery)

**Условия retry:**
- `429 Too Many Requests` (rate limit)
- `5xx Server Error`
- `httpx.ConnectError` (connection timeout)
- `httpx.ReadTimeout`

**Не retry:**
- `400 Bad Request` (невалидный запрос)
- `401 Unauthorized` (неверный токен)
- `404 Not Found` (неверный endpoint)

**Параметры:**
```python
max_delivery_attempts = 3
backoff_seconds = [1.0, 2.0, 4.0]  # Экспоненциальный
```

---

## Rate Limiting

**Текущая реализация:** Нет встроенного rate limiting.

**Рекомендации:**
- Wappi API имеет собственный rate limit (вернёт `429`)
- wappi-module обрабатывает `429` через retry с backoff
- Для защиты от DDoS используйте внешний reverse proxy (nginx, Cloudflare)

---

## Monitoring & Debugging

### Ключевые логи для отладки

#### Transport Delivery

```
transport.delivery.preparing    # Начало доставки
wappi.api.sending_request       # Запрос к Wappi API (с полными параметрами)
wappi.api.message_sent          # Успешный ответ
transport.delivery.delivered    # Успешная доставка
```

#### Webhook Handling

```
wappi.webhook.received          # Входящий webhook
sales_agent.forward.success     # Успешный форвард
wappi.webhook.forwarded         # Завершение обработки
```

#### Errors

```
transport.delivery.failed       # Ошибка доставки
wappi.api.http_error            # HTTP ошибка от Wappi
wappi.webhook.forward_failed    # Ошибка форварда в Sales Agent
connector.reload.failed         # Ошибка загрузки конфигов
```

### Debugging checklist

1. **404 на webhook:** Проверьте `connector.reload.completed` — загружены ли коннекторы?
2. **401 от Wappi:** Проверьте `wappi_token` в БД backend
3. **profile_id incorrect:** Проверьте что `wappi_profile_id` — полный UUID (36 символов)
4. **Нет recipient:** Проверьте что Sales Agent передаёт `metadata.chat_id`
5. **422 от Sales Agent:** Проверьте формат `messages` (массив vs объект)

---

**Документ обновлён:** 2024-11-21  
**Версия модуля:** 0.1.0

