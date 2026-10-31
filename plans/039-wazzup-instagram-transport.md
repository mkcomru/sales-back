# 039 — Wazzup Instagram Transport: Full Pipeline Integration

## Зачем это делаем

Сейчас у нас нет поддержки Instagram как канала продаж. Wazzup24 — это платформа,
через которую бизнес подключает Instagram DM к CRM. Добавив wazzup-транспорт,
мы открываем для клиентов возможность подключить Instagram-аккаунт и получить
полноценного AI-агента в директе — без каких-либо изменений в логике продаж.

После реализации: клиент добавляет коннектор типа `wazzup` с `api_key` + `channel_id`,
пишет ему пользователь в Instagram → агент отвечает. Весь пайплайн тот же, что у wappi.

---

## Текущее состояние

**Уже готово (не трогаем):**

- `wazzup-instagram` в `CONNECTOR_TYPE_CATALOG` (libs/common)
- `BackendTransportWazzupSettings` + `transport.wazzup` в common config
- `WazzupModuleSettings` в common config
- Структура модуля: main, routes, connectors, lifespan/eventing

**Требует изменений в wazzup-module:**

- `services/wazzup_api.py` — нет `register_webhook()`, `crmMessageId`, хардкод `chatType`
- `services/inbound.py` — неправильная детекция роли, нет sender info, нет `provider_message_id`
- `connectors/manager.py` — нет `get_by_channel_id()`, нет авторегистрации вебхука
- `transport/service.py` — не передаёт `crmMessageId` и `chat_type` в API
- `routes.py` — доступ к приватному `_connectors`

**Требует изменений в backend:**

- `ConnectorType` enum — нет `WAZZUP`
- `transport_client.py` — нет routing для `"wazzup"`
- Миграция

**Требует изменений в common:**

- `WazzupModuleSettings` — нет `webhook_url`

---

## Wazzup API: что нам нужно

### Регистрация вебхука

```
PATCH https://api.wazzup24.com/v3/webhooks
Authorization: Bearer {api_key}

{
  "webhooksUri": "https://our-domain.com/wazzup/webhook",
  "subscriptions": {
    "messagesAndStatuses": true
  }
}
```

Нужно вызывать при добавлении нового коннектора (в `ConnectorManager.reload()`).

### Формат входящего вебхука (messages)

Ключевые поля из `messages[]`:

```
messageId     — provider_message_id (uuid)
channelId     — по нему находим коннектор
chatType      — "instagram", "whatsapp", "telegram" и др.
chatId        — conversation_id / user_id
dateTime      — timestamp (ISO 8601)
type          — "text", "image", "audio", "video", "document", ...
isEcho        — false=входящее (USER), true=исходящее
sentFromApp   — true=менеджер написал из приложения Wazzup
text          — текст сообщения (может отсутствовать у медиа)
contentUri    — ссылка на медиа
contact.name
contact.username  — только для Telegram
contact.phone     — только для Telegram/MAX
isDeleted     — true=сообщение удалено, пропускаем
isEdited      — true=сообщение отредактировано, пропускаем
```

**Логика определения роли:**

```
isEcho=false                         → USER (входящее от клиента)
isEcho=true AND sentFromApp=true     → MANAGER (менеджер написал из Wazzup)
isEcho=true AND sentFromApp=false    → пропускаем (эхо нашего API-ответа)
isDeleted=true или isEdited=true     → пропускаем
```

### Отправка сообщения

```
POST https://api.wazzup24.com/v3/message
Authorization: Bearer {api_key}

{
  "channelId": "...",
  "chatId": "...",
  "chatType": "instagram",
  "text": "...",
  "crmMessageId": "{correlation_id}"  ← идемпотентность на стороне Wazzup (60 сек)
}
```

`crmMessageId` — строка, уникальная для каждого сообщения. Передаём `correlation_id` из payload.
Важно: окно идемпотентности у Wazzup — 60 секунд, у нас — 24 часа через `_IdempotencyStore`. Оба нужны.

---

## Шаги реализации

### 1. common — `WazzupModuleSettings`: добавить `webhook_url`

**Файл:** `libs/common/src/common/config.py`, класс `WazzupModuleSettings`

```python
webhook_url: AnyHttpUrl | None = Field(
    default=None,
    alias="WAZZUP_MODULE_WEBHOOK_URL",
    description="Public URL for Wazzup webhooks (e.g. https://our-domain.com/wazzup/webhook).",
)
```

---

### 2. `services/wazzup_api.py` — три изменения

**а) `register_webhook(api_key, webhook_uri)`**

```python
async def register_webhook(self, *, api_key: str, webhook_uri: str) -> None:
    """Register webhook URI with Wazzup. Call when connector is added."""
    url = f"{self._base_url}/webhooks"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "webhooksUri": webhook_uri,
        "subscriptions": {"messagesAndStatuses": True},
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.patch(url, headers=headers, json=payload)
        if response.status_code >= 400:
            raise WazzupApiError(f"Webhook registration failed {response.status_code}: {response.text}")
```

**б) `chat_type` параметр в `send_message()`**

Убрать хардкод `"chatType": "instagram"`, принимать `chat_type: str` как аргумент.

**в) `crmMessageId` параметр в `send_message()`**

Добавить `crm_message_id: str | None = None`, включать в payload если задан.

---

### 3. `connectors/manager.py` — два изменения

**а) Принять `WazzupApiClient` + `webhook_url` в конструкторе**

```python
def __init__(
    self,
    settings: Settings,
    backend: WazzupBackendClient,
    wazzup_client: WazzupApiClient,
) -> None:
    ...
    self._wazzup_client = wazzup_client
    self._webhook_url = settings.webhook_url
```

**б) Регистрировать вебхук при добавлении коннектора**

В блоке `for connector_id in new_ids - existing_ids:` после `log.info("connector.added")`:

```python
if self._webhook_url:
    try:
        await self._wazzup_client.register_webhook(
            api_key=new_configs_dict[connector_id].wazzup_api_key.get_secret_value(),
            webhook_uri=str(self._webhook_url),
        )
        log.info("connector.webhook.registered", connector_id=connector_id)
    except WazzupApiError as exc:
        log.error("connector.webhook.registration_failed", connector_id=connector_id, error=str(exc))
else:
    log.warning("connector.webhook.url_not_configured", connector_id=connector_id)
```

**в) Публичный метод `get_by_channel_id()`**

```python
def get_by_channel_id(self, channel_id: str) -> WazzupConnectorConfig | None:
    for connector in self._connectors.values():
        if connector.channel_id == channel_id:
            return connector
    return None
```

---

### 4. `api/routes.py` — использовать публичный метод

Удалить `_find_connector_by_channel()`, заменить на `manager.get_by_channel_id(channel_id)`.

---

### 5. `services/inbound.py` — полная переработка нормализации

**Логика `_normalize_message()`:**

```python
# Пропускаем удалённые и отредактированные
if message.get("isDeleted") or message.get("isEdited"):
    return None

is_echo = message.get("isEcho", False)
sent_from_app = message.get("sentFromApp", False)

# Эхо нашего собственного API-ответа — пропускаем
if is_echo and not sent_from_app:
    return None

# Менеджер написал из приложения Wazzup
if is_echo and sent_from_app:
    role = MessageRole.MANAGER
else:
    role = MessageRole.USER

chat_id = _as_str(message.get("chatId"))
if not chat_id:
    return None

text = _as_str(message.get("text"))
# TODO: media (contentUri) — пока только текст

if not text:
    return None

contact = message.get("contact") or {}

return InboundEnvelope(
    conversation_id=chat_id,
    user_id=chat_id,
    text=text,
    ts=_parse_ts(message.get("dateTime")),
    artifact_ids=[],
    audio=None,
    role=role,
    is_historical=False,
    sender_name=_as_str(contact.get("name")),
    sender_username=_as_str(contact.get("username")),
    sender_phone=_as_str(contact.get("phone")),
    provider_message_id=_as_str(message.get("messageId")),
    extra={"_manager_outgoing": True} if role == MessageRole.MANAGER else {},
)
```

Вынести `_parse_ts()` как отдельную функцию (ISO 8601 → float).

---

### 6. `transport/service.py` — передавать `chat_type` и `crmMessageId`

В `_deliver_replies()`:

```python
chat_type = connector.channel_type  # "instagram", "whatsapp", etc.

await self._send_with_retry(
    wazzup_client=wazzup_client,
    api_key=connector.wazzup_api_key.get_secret_value(),
    channel_id=connector.channel_id,
    chat_id=recipient,
    chat_type=chat_type,
    text=text,
    crm_message_id=f"{payload.correlation_id}:{index}",  # уникально per reply
    ...
)
```

В `_send_with_retry()` прокинуть `chat_type` и `crm_message_id` в `wazzup_client.send_message()`.

---

### 7. `main.py` — передать `wazzup_client` в `ConnectorManager`

```python
connector_manager = ConnectorManager(settings, backend_client, wazzup_client)
```

---

### 8. Backend — `ConnectorType` enum

**Файл:** `apps/backend/src/backend/modules/transport/models.py`

```python
class ConnectorType(str, Enum):
    TELEGRAM = "telegram"
    WAPPI = "wappi"
    WAZZUP = "wazzup"   # ← новое
    CUSTOM = "custom"
```

---

### 9. Backend — transport routing

**Файл:** `apps/backend/src/backend/modules/messages/transport_client.py`

```python
case "wazzup":
    if not self._settings.transport.wazzup.url:
        raise TransportClientError(f"Transport endpoint not configured for type '{connector_type}'")
    return str(self._settings.transport.wazzup.url).rstrip("/")
```

---

### 10. Backend — Aerich migration

```bash
cd apps/backend
uv run aerich migrate --name add_wazzup_connector_type
```

В сгенерированном файле вручную добавить schema prefix:

```sql
-- Автоматически (неверно)
ALTER TABLE "connector" MODIFY COLUMN "type" ...
-- Исправить на
ALTER TABLE "backend"."connector" MODIFY COLUMN "type" ...
```

---

### 11. Тесты wazzup-module

По образцу `apps/wappi-module/tests/`. Покрыть:

- `tests/conftest.py` — settings, connector_config, mock_manager, mock_inbound_client, client
- `tests/domains/api/test_routes.py` — health, admin reload, transport delivery, webhook (valid/unknown channel/no messages)
- `tests/domains/connectors/test_manager.py` — reload, get, get_by_channel_id, webhook registration on new connector
- `tests/domains/services/test_inbound.py`:
  - incoming text → USER role
  - isEcho=true, sentFromApp=true → MANAGER role
  - isEcho=true, sentFromApp=false → None (пропускаем)
  - isDeleted=true → None
  - no chatId → None
  - no text → None
  - sender_name/username из contact
  - provider_message_id из messageId
- `tests/domains/services/test_wazzup_api.py` — send_message (success, 4xx, network error), register_webhook
- `tests/domains/transport/test_service.py` — delivery success (202), duplicate (409), auth failure, retry, crmMessageId передаётся

---

## Env vars (добавить)

```bash
WAZZUP_MODULE_WEBHOOK_URL=https://our-domain.com/wazzup/webhook
TRANSPORT__WAZZUP__URL=http://wazzup-module:8004
```

---

## Порядок деплоя

1. `aerich upgrade` на бекенде
2. Деплой backend (новый `ConnectorType.WAZZUP` + routing)
3. Деплой wazzup-module
4. Создать коннектор в БД: `type=wazzup`, `channel_type=instagram`, `config={wazzup_api_key, channel_id}`
5. На первом `reload()` модуль сам зарегистрирует вебхук в Wazzup24
