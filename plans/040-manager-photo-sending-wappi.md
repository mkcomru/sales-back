# 040 — Отправка медиа менеджером (фото, аудио, документы)

## Objective

Менеджер с фронта отправляет медиафайлы клиенту через существующий пайплайн сообщений: изображения, аудио, документы. Медиа проходит через Backend и доставляется транспортами. Scope: Wappi (WhatsApp, Telegram, VK), Telegram Bot, фронт, тесты. **Out of scope:** поддержка со стороны sales-agent.

## Зачем это делаем

- **Проблема**: Менеджер может писать клиенту только текст. Чтобы отправить фото товара, прайс-лист или скриншот — приходится переключаться в мессенджер напрямую.
- **Ценность**: Полноценный чат из CRM. Менеджер работает в одном окне — текст, фото, аудио, документы. Паттерн `artifact_id` переиспользуется для всех типов медиа.

---

## Design Decisions

### Передача медиа: artifact_id + presigned URL (не relay через Backend)

**Контекст:** Изначально был выбран неправильный подход — relay файлов через Backend (транспорт скачивает через GET /internal/artifacts). Это была ошибка архитектуры с моей стороны. Сейчас есть возможность реализовать правильно — через presigned URL.

**Выбрано:** Backend передаёт `artifact_id` в `attachments`. Транспорт **не** тянет байты через Backend: вместо этого запрашивает presigned URL, затем скачивает напрямую из S3.

**Зачем presigned URL:**
- Backend не должен брать на себя нагрузку по передаче больших файлов — S3 как раз для того, чтобы служить прямым источником медиа.
- Раньше или позже на presigned URL всё равно придётся перейти; реализация в этой таске упростит дальнейшую миграцию всего S3-функционала в бэкенде.

**Flow:**
1. Transport вызывает Backend: `GET /internal/artifacts/{artifact_id}/presigned-url` (auth: `X-Service-Key`)
2. Backend проверяет права (connector, company, artifact принадлежит нужному контексту и т.п.)
3. Backend генерирует presigned GET URL для S3 и возвращает `{ "url": "...", "expires_in": 3600 }`
4. Transport скачивает файл по URL напрямую из S3, конвертирует при необходимости (base64 для Wappi) и отправляет через API провайдера

**Важно:** Endpoint для выдачи presigned URL защищён авторизацией и валидацией прав так же, как и любой другой manager endpoint. Разница только в том, что Backend не проксирует байты, а выдаёт временный URL для прямого доступа.

### Фото/медиа без подписи

Ослабить валидацию `TransportDeliveryPayload.replies`: разрешить пустой `replies` если есть `attachments` (model_validator).

### Формат attachments (обязательно Pydantic)

**Перед стандартизацией:** проверить всех потребителей `attachments` и либо оставить поле без потребителей, либо перевести их на новый контракт.

Текущие потребители `attachments`:
- `TransportDeliveryPayload.attachments` — transport_client, Wappi/Telegram delivery
- `ChatMessageCreateRequest.attachments` — backend chat schemas
- `ChatMessage.attachments` — модель, schemas, routers

→ Нужна миграция потребителей на типизированный контракт.

Типизированный контракт (Pydantic):

```python
class AttachmentDescriptor(BaseModel):
    artifact_id: str
    type: Literal["image", "audio", "video", "document"]
    mime_type: str
    caption: str | None = None
```

---

## Connector contracts (connector-contracts.mdc)

**Обязательно:** следовать [connector-contracts.mdc](../.cursor/rules/connector-contracts.mdc):
- Регистрировать capabilities в `libs/common/src/common/transport/registry.py` — не в модуле
- Добавлять `ConnectorCapability.OUTBOUND_MEDIA` **только** для коннекторов, где реализация завершена
- Hub-транспорты: compound keys `{transport}-{channel}`

**Коннекторы в Wappi (внутри модуля 3 шт.):**
- `wappi-whatsapp`
- `wappi-telegram`
- `wappi-vk`

**Все 4 коннектора для проверки:**
1. Telegram Bot (`telegram`)
2. Wappi Telegram (`wappi-telegram`)
3. Wappi WhatsApp (`wappi-whatsapp`)
4. Wappi VK (`wappi-vk`)

**Capabilities:** выкатывать равномерно — Wappi (3 платформы) и Telegram Bot должны получить `OUTBOUND_MEDIA` по мере реализации.

---

## Implementation Steps

### Step 0: Audit потребителей attachments

Проверить использование `attachments`:
- `common/models/transport.py` → TransportDeliveryPayload
- `backend/modules/chat/schemas.py` → ChatMessageCreateRequest
- `backend/modules/chat/models.py` → ChatMessage
- `backend/modules/chat/service.py`, `routers.py`, `repository.py`
- Wappi `sales_agent.py` (inbound, не outbound)

**Решение:** если потребители есть — перевести на `AttachmentDescriptor` (Pydantic). Если нет — стандартизировать сразу.

### Step 1: Pydantic-модель AttachmentDescriptor и обновление TransportDeliveryPayload

**File:** `libs/common/src/common/models/transport.py`

- Добавить `AttachmentDescriptor(BaseModel)` с `artifact_id`, `type`, `mime_type`, `caption`
- `TransportDeliveryPayload.attachments`: `list[AttachmentDescriptor] | None = None`
- Ослабить `replies`: model_validator — либо `replies`, либо `attachments` непусты

### Step 2: Публичный upload endpoint для менеджеров

**File:** `apps/backend/src/backend/modules/s3_storage/routers.py`

```
POST /companies/{company_id}/artifacts/upload
Auth: CompanyManagerDep
Body: multipart (file, file_type)
Response: ArtifactUploadResponse { artifact_id }
```

Поддержка типов: image, audio, video, document (MIME и расширения по конфигу).

### Step 3: Прокидывание artifact_ids и attachments в chat flow

**Files:** `chat/routers.py`, `chat/service.py`, `chat/repository.py`

- `payload.attachments` → `artifact_ids` в `create_message`
- `notify_sales_agent_manager_message` — передать `attachments` в transport payload

### Step 4: presigned URL endpoint + get_artifact_download_url в BaseTransportBackendClient

**Backend:** `apps/backend/src/backend/modules/s3_storage/routers.py` (или отдельный internal router)

```
GET /internal/artifacts/{artifact_id}/presigned-url
Auth: X-Service-Key
Response: { "url": "https://s3...?Signature=...", "expires_in": 3600 }
```

- Проверка прав: artifact существует, принадлежит компании/треду из контекста
- Генерация presigned GET URL (boto3 `generate_presigned_url`) с разумным TTL (напр. 1 ч, достаточно для retry)

**File:** `libs/common/src/common/transport/base_backend_client.py`

`get_artifact_download_url(artifact_id: str) -> str` — вызывает endpoint, возвращает URL.  
`download_artifact(artifact_id: str) -> bytes` — обёртка: получает URL → GET по URL → возвращает bytes (для совместимости с transport service).

### Step 5: Wappi — send_image, send_audio, send_document

**File:** `apps/wappi-module/src/wappi_module/services/wappi_api.py`

Методы под каждый тип медиа (image, audio, document), аналогично `send_message`.

### Step 6: Wappi transport — обработка attachments

**File:** `apps/wappi-module/src/wappi_module/transport/service.py`

`_deliver_replies`: после текста обработать `payload.attachments` — скачать, конвертировать, вызвать соответствующий send_* по `type`.

### Step 7: Registry — OUTBOUND_MEDIA для Wappi (все 3)

**File:** `libs/common/src/common/transport/registry.py`

Добавить `ConnectorCapability.OUTBOUND_MEDIA` в:
- `wappi-whatsapp`
- `wappi-telegram`
- `wappi-vk`

### Step 8: Telegram Bot module — capabilities и обработка attachments

**File:** `apps/telegram-module/` — реализовать доставку медиа (aiogram send_photo, send_audio, send_document), добавить `OUTBOUND_MEDIA` в registry для `telegram`.

Capabilities выкатывать равномерно: после Wappi — telegram.

### Step 9: Фронт (sales-front)

- UI для загрузки и отправки медиа (upload → artifact_id → attachments в запросе)
- Отображение вложений в истории чата

### Step 10: Тесты

- Backend: upload, create_message с attachments, transport payload
- Wappi/Telegram: delivery с attachments
- Фронт: E2E/интеграционные при необходимости

---

## Acceptance Criteria

1. Менеджер загружает фото/аудио/документ → получает `artifact_id`
2. Отправка с `attachments: [{artifact_id, type, mime_type}]` → сообщение с `artifact_ids`
3. Backend роутит в транспорт с типизированными `attachments`
4. Wappi (whatsapp, telegram, vk) и Telegram Bot доставляют медиа
5. Работает без подписи и с подписью (caption)
6. Фронт: upload UI, отображение в истории
7. Все 4 коннектора проверены
8. OUTBOUND_MEDIA зарегистрирован по connector-contracts

## Out of Scope

- **sales-agent** — поддержка отправки медиа от AI-ассистента (отдельный план)
- Превью/thumbnails на фронте (по желанию)
- Множественные вложения в одном сообщении (архитектура поддерживает, лимиты — отдельно)

---

## Developer Note: Instagram

Параллельно ведётся разработка коннектора для Instagram. При добавлении Instagram в каталог коннекторов необходимо обеспечить поддержку тех же capabilities (включая `OUTBOUND_MEDIA`) в соответствии с п.5 — выкатывать capabilities равномерно по всем платформам.
