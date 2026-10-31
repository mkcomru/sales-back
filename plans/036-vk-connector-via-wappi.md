# 036 — VK-коннектор через Wappi

**Задача:** [DEVS-197](https://linear.app/pulsefirst/issue/DEVS-197/dobavit-novyj-vk-konnektor)
**Ветка:** `devs-197-dobavit-novii-vk-konnektor`

---

## Зачем это делаем

### Проблема для бизнеса

Сейчас платформа поддерживает два канала коммуникации с клиентами: WhatsApp и Telegram (личные сообщения) — оба через Wappi API. ВКонтакте — одна из крупнейших платформ в РФ, и у многих бизнесов значительная часть клиентской базы общается именно там. Без VK-коннектора эти клиенты остаются вне зоны автоматизации.

### Что станет возможным

1. **Для пользователей платформы:** подключить VK-аккаунт через Wappi и получить AI-продажника, который автоматически обрабатывает входящие сообщения из VK — точно так же, как сейчас работает WhatsApp и Telegram.
2. **Для UI:** в списке каналов появится новый тип "VK (Wappi)" с честным набором capabilities.
3. **Для архитектуры:** VK подключается как третий канал в hub-стиле wappi-module. Никаких новых сервисов — используем существующую инфраструктуру (менеджер коннекторов, delivery, sync). Это подтверждает, что hub-архитектура работает как задумано.

---

## Scope

**Что входит:**
- Регистрация `wappi-vk` в каталоге коннекторов
- Поддержка VK API-эндпоинтов Wappi (`/vkapi/...`) в `WappiApiClient`
- Нормализация входящих VK-сообщений (webhooks)
- Отправка исходящих сообщений в VK
- Синхронизация истории через `/vkapi/sync/chats/get` и `/vkapi/sync/messages/get`

**Что НЕ входит:**
- Новые сервисы или модули — всё внутри wappi-module
- Поддержка медиа (картинки, файлы) — на первом этапе только текст + голос
- Изменения в backend routing — `type="wappi"` уже роутится в wappi-module

---

## Анализ Wappi VK API (из Postman-коллекции)

Wappi API для VK использует префикс `/vkapi/` (аналогично `/tapi/` для Telegram и `/api/` для WhatsApp).

### Эндпоинты

| Операция | Эндпоинт | Метод |
|----------|----------|-------|
| Отправить текст | `/vkapi/async/message/send` | POST |
| Отправить ответ | `/vkapi/sync/message/reply` | POST |
| Отправить файл по URL | `/vkapi/sync/message/file/url/send` | POST |
| Отправить картинку | `/vkapi/sync/message/img/send` | POST |
| Отправить документ | `/vkapi/sync/message/document/send` | POST |
| Отправить видео | `/vkapi/sync/message/video/send` | POST |
| Отправить аудио | `/vkapi/sync/message/audio/send` | POST |
| v2 отправка (async) | `/vkapi/v2/async/message/send` | POST |
| Получить чаты | `/vkapi/sync/chats/get` | POST (с filter в body) |
| Получить сообщения | `/vkapi/sync/messages/get` | GET |
| Получить вебхук | `/vkapi/webhook/url/get` | GET |
| Установить вебхук | `/vkapi/webhook/url/set` | POST |
| Удалить вебхук | `/vkapi/webhook/url/delete` | DELETE |
| Типы вебхуков | `/vkapi/webhook/types/set` | POST |
| Получить задачу | `/vkapi/task/get` | GET |
| Получить задачи | `/vkapi/tasks/get` | GET |

### Формат запроса (send text)

```json
{
  "body": "test message",
  "recipient": "863567278"
}
```

Авторизация: `Authorization: {{token}}`, query-параметр `profile_id={{profile_id}}` — **идентично** WhatsApp и Telegram.

### Вывод

API-контракт VK **совпадает** с WhatsApp/Telegram — те же параметры (`body`, `recipient`, `profile_id`, `Authorization`). Разница только в URL-префиксе (`/vkapi/` вместо `/api/` или `/tapi/`). Это значит, что `WappiConnectorConfig` менять не нужно — `wappi_token` + `wappi_profile_id` + `channel_type="vk"` достаточно.

---

## Ключевые решения

### 1. Роутинг эндпоинтов по channel_type

Сейчас `WappiApiClient` определяет эндпоинт бинарно:
```python
if "telegram" in channel_type.lower():
    url = f"{self._base_url}/tapi/..."
else:
    url = f"{self._base_url}/api/..."  # WhatsApp — дефолт
```

**Решение:** рефакторинг на `match/case` или маппинг с явным роутингом для каждого канала. Не используем `else` как catch-all — fail fast если channel_type неизвестный.

```python
_CHANNEL_API_PREFIX: dict[str, str] = {
    "telegram": "tapi",
    "whatsapp": "api",
    "vk": "vkapi",
}

def _api_prefix(self, channel_type: str) -> str:
    prefix = _CHANNEL_API_PREFIX.get(channel_type.lower())
    if prefix is None:
        raise WappiApiError(f"Unsupported channel_type: {channel_type}")
    return prefix
```

Это убирает неявный fallback на WhatsApp и делает добавление нового канала однострочным.

### 2. Нормализация входящих VK-сообщений

В `BackendInboundClient._normalize_message()` сейчас:
```python
is_telegram = "telegram" in channel_type.lower()
is_whatsapp = "whatsapp" in channel_type.lower() or "whats_app" in channel_type.lower()
```

Для VK нужно определить, какой `msg_type` приходит в вебхуках. Скорее всего, тот же формат что у WhatsApp (`"chat"` для текста), но это нужно проверить на реальных вебхуках.

**Решение:** добавить `is_vk = "vk" in channel_type.lower()` и маппинг. На первом этапе — аналогично WhatsApp (тип `"chat"` для текста).

### 3. Capabilities VK

VK через Wappi поддерживает sync-эндпоинты (чаты и сообщения), поэтому включаем `HISTORY_SYNC` сразу:

```python
"wappi-vk": ConnectorTypeCatalogEntry(
    connector_type="wappi-vk",
    display_name="VK (Wappi)",
    description="ВКонтакте через Wappi API",
    managed=True,
    supported_capabilities=[
        ConnectorCapability.INBOUND_TEXT,
        ConnectorCapability.OUTBOUND_TEXT,
        ConnectorCapability.HISTORY_SYNC,
        # INBOUND_VOICE, INBOUND_AUDIO — добавим после проверки вебхуков
    ],
)
```

### 4. HTTP-метод для get_chats_list

| Канал | Метод | Эндпоинт |
|-------|-------|----------|
| Telegram | GET | `/tapi/sync/chats/get` |
| WhatsApp | POST | `/api/sync/chats/get` (пустой body или `{}`) |
| VK | POST | `/vkapi/sync/chats/get` (body: `{"filter": {"ids": [...]}}`) |

VK и WhatsApp оба используют POST. VK дополнительно поддерживает фильтрацию по chat IDs в body. Текущая реализация `get_chats_list` уже отправляет `json={}` для POST — для VK это будет работать (получим все чаты). Фильтрация по IDs — опциональная оптимизация, можно добавить позже.

---

## Шаги реализации

### Шаг 1: Регистрация в каталоге

**Файл:** `libs/common/src/common/transport/registry.py`

Добавить `"wappi-vk"` в `CONNECTOR_TYPE_CATALOG`:

```python
"wappi-vk": ConnectorTypeCatalogEntry(
    connector_type="wappi-vk",
    display_name="VK (Wappi)",
    description="ВКонтакте через Wappi API",
    managed=True,
    supported_capabilities=[
        ConnectorCapability.INBOUND_TEXT,
        ConnectorCapability.OUTBOUND_TEXT,
        ConnectorCapability.HISTORY_SYNC,
    ],
),
```

Валидация в `main.py` подхватит автоматически — фильтр `startswith("wappi")`.

**Зависит от:** ничего.

---

### Шаг 2: Рефакторинг роутинга эндпоинтов в WappiApiClient

**Файл:** `apps/wappi-module/src/wappi_module/services/wappi_api.py`

Заменить бинарный `if/else` на маппинг `_CHANNEL_API_PREFIX` во всех методах:
- `send_message()` — строка 38-41
- `get_chats_list()` — строка 126-131
- `get_chat_messages()` — строка 218-221
- `download_media()` — строка 277-280

Вынести в приватный метод `_api_prefix(channel_type)` с fail-fast на неизвестный тип.

Для `get_chats_list` — VK использует POST (как WhatsApp), с поддержкой filter в body.

**Зависит от:** ничего (можно параллельно с шагом 1).

---

### Шаг 3: Нормализация входящих VK-сообщений

**Файл:** `apps/wappi-module/src/wappi_module/services/sales_agent.py`

В `_normalize_message()` (строка 137-144):

```python
is_telegram = "telegram" in channel_type.lower()
is_whatsapp = "whatsapp" in channel_type.lower() or "whats_app" in channel_type.lower()
is_vk = "vk" in channel_type.lower()

if is_telegram and msg_type == "text":
    text = _as_str(message.get("body"))
elif is_whatsapp and msg_type == "chat":
    text = _as_str(message.get("body"))
elif is_vk and msg_type in ("chat", "text"):
    text = _as_str(message.get("body"))
```

VK через Wappi скорее всего использует тот же формат вебхуков. Принимаем оба типа (`"chat"` и `"text"`) для safety, так как точный формат станет известен при тестировании.

**Зависит от:** ничего (можно параллельно).

---

### Шаг 4: Адаптация sync-провайдера

**Файл:** `apps/wappi-module/src/wappi_module/sync/provider.py`

VK поддерживает sync-эндпоинты:
- Чаты: `POST /vkapi/sync/chats/get` (с опциональным `{"filter": {"ids": [...]}}` в body)
- Сообщения: `GET /vkapi/sync/messages/get?chat_id=...&limit=...&offset=...&order=...`

После рефакторинга шага 2 (`_api_prefix`) sync заработает автоматически для VK. Нужно:
- Убедиться, что `transform_message()` корректно обрабатывает VK-формат ответов
- VK чаты через POST (как WhatsApp) — текущая логика `get_chats_list` уже обрабатывает POST-ветку

**Зависит от:** шаг 2.

---

### Шаг 5: Тестирование

**Что тестировать:**

1. **Unit-тесты `WappiApiClient`:**
   - `_api_prefix("vk")` → `"vkapi"`
   - `_api_prefix("telegram")` → `"tapi"`
   - `_api_prefix("whatsapp")` → `"api"`
   - `_api_prefix("unknown")` → `WappiApiError`
   - `send_message(channel_type="vk")` формирует правильный URL

2. **Unit-тесты нормализации:**
   - VK-сообщение с `msg_type="chat"` → корректный `InboundEnvelope`
   - VK-сообщение с `msg_type="text"` → корректный `InboundEnvelope`

3. **Catalog validation:**
   - `"wappi-vk"` в каталоге
   - `resolve_catalog_key("wappi", "vk")` → `"wappi-vk"`

4. **Интеграционное (ручное):**
   - Создать коннектор `type=wappi`, `channel_type=vk` в БД
   - Отправить тестовый вебхук → проверить forward в backend
   - Отправить исходящее сообщение → проверить доставку через `/vkapi/async/message/send`

---

## Файлы для изменения (полный список)

| Файл | Что меняется |
|------|-------------|
| `libs/common/src/common/transport/registry.py` | Добавить `"wappi-vk"` в каталог |
| `apps/wappi-module/src/wappi_module/services/wappi_api.py` | Рефакторинг if/else → маппинг + VK-эндпоинты |
| `apps/wappi-module/src/wappi_module/services/sales_agent.py` | Добавить `is_vk` в нормализацию |

### Файлы БЕЗ изменений (и почему)

| Файл | Почему не трогаем |
|------|-------------------|
| `connectors/models.py` | `WappiConnectorConfig` уже generic — `channel_type="vk"` работает |
| `connectors/manager.py` | Generic, работает с любым `channel_type` |
| `transport/service.py` | Generic delivery, роутит по connector config |
| `main.py` | Фильтр `startswith("wappi")` подхватит `wappi-vk` |
| `api/routes.py` | Webhook-хендлер generic — работает с любым connector |
| `backend transport_client.py` | `type="wappi"` уже роутится корректно |
| `config/settings.py` | Настройки общие для всех каналов wappi |

---

## Risks / Open Questions

1. **Формат VK-вебхуков** — точные поля (`msg_type`, `fromMe`, `chatId`, `from_where`) станут известны только при реальном тестировании. Код пишем по аналогии с WhatsApp/Telegram, корректируем при тестировании.

2. **Голосовые сообщения VK** — VK поддерживает голосовые, но формат (`ptt`, `ogg`, `mp3`) может отличаться от WhatsApp/Telegram. На первом этапе не включаем `INBOUND_VOICE` — добавим после проверки.

3. **Rate limits** — Wappi может иметь разные лимиты для VK API. Текущий `get_rate_limit() → 2.0` из sync-провайдера может потребовать корректировки.
