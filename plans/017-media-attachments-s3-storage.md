# Plan 017 — Media Attachments & S3 Storage

## Objective

Реализовать работу с вложениями (начиная с голосовых) с ссылочной логикой через S3-хранилище. Коннекторы загружают файлы в S3 через backend, получают `artifact_id`, и далее оперируют только этим идентификатором.

## Problem Statement

**Текущее состояние:**
- Файлы передаются как base64 в JSON через `InboundEnvelope.audio.bytes_base64` (неэффективно, ограничения размера)
- Backend не сохраняет файлы в S3 при получении сообщений
- Нет концепции `artifact_id` — используется S3 key напрямую (если вообще используется)
- Нет API endpoints для работы с артефактами
- Транскрипция выполняется каждый раз без кеширования (результат не сохраняется в БД)
- Нет абстракции на уровне модели для работы с файлами
- Коннекторы сами скачивают и конвертируют файлы, нет единого формата

**Требования:**
- Доступ к S3 ТОЛЬКО у backend — ни Sales-Agent, ни коннекторы не лезут напрямую
- Pre-processing endpoint для загрузки файлов в S3 перед отправкой сообщения
- Ссылочная модель: коннекторы оперируют только `artifact_id`
- Транскрипция в Sales-Agent с кешированием в Backend
- Единый формат файлов (mp3 для голосовых, конвертация в коннекторах)
- Голосовые — первый кейс, но архитектура должна поддерживать другие типы

## Target Architecture

```
INBOUND FLOW (Voice Message):
  ┌─────────────┐  1. Download voice    ┌─────────────┐
  │  Connector  │ ────────────────────► │  Telegram   │
  │ (Telegram) │                        │  Bot API    │
  └──────┬──────┘                        └─────────────┘
         │
         │ 2. Convert to mp3
         │
         │ 3. Upload to Backend
         ▼
  ┌─────────────┐   POST /artifacts/    ┌─────────────┐
  │  Connector  │      upload           │   Backend   │
  │             │ ────────────────────► │  (S3 Store) │
  └──────┬──────┘                        └──────┬──────┘
         │                                      │
         │ ◄───────────────────────────────────┘
         │ 4. artifact_id
         │
         │ 5. Message with artifact_id
         ▼
  ┌─────────────┐   POST /messages/     ┌─────────────┐
  │  Connector  │      inbound          │   Backend   │
  │             │ ────────────────────► │  (Router)   │
  └─────────────┘                        └──────┬──────┘
                                                │
                                                │ 6. Save message with artifact_id
                                                │
                                                │ 7. Forward to Sales-Agent
                                                ▼
                                         ┌─────────────┐
                                         │Sales Agent  │
                                         │             │
                                         │ 8. GET /artifacts/{id}
                                         │             │
                                         └──────┬──────┘
                                                │
                                                │ 9. Download file
                                                ▼
                                         ┌─────────────┐
                                         │   Backend   │
                                         │  (S3 Store) │
                                         └──────┬──────┘
                                                │
                                                │ 10. Transcribe
                                                ▼
                                         ┌─────────────┐
                                         │Sales Agent  │
                                         │  (STT)      │
                                         └──────┬──────┘
                                                │
                                                │ 11. POST /messages/{id}/transcription
                                                ▼
                                         ┌─────────────┐
                                         │   Backend   │
                                         │  (Cache)    │
                                         └─────────────┘
```

## Proposed Steps

### Phase 1: Backend Infrastructure

1. **Расширить модель ChatMessage:**
   - Добавить типы в `ChatMessageType`: `AUDIO`, `IMAGE`, `VIDEO`
   - Добавить поле `artifact_ids: JSONField(default=list)` для хранения списка S3 keys (строк)
     - В PostgreSQL хранится как JSONB массив строк: `["company_123/voice/abc.mp3", ...]`
     - Аналогично существующему полю `attachments` (используется тот же подход)
   - Использовать существующее поле `content` для хранения транскрипции (не добавлять новое поле)
   - Создать миграцию для новых полей

2. **API Endpoints:**
   - `POST /api/v1/internal/artifacts/upload` — pre-processing для коннекторов
     - Авторизация: `X-Service-Key` + `X-Connector-Id` (через `get_managed_connector`)
     - Принимает multipart/form-data: `file` (File), `file_type` (str), `company_id` (int)
     - Валидация размера файла (макс. 50MB)
     - Использует `S3Client.upload_file()` → возвращает S3 key как `artifact_id`
     - Возвращает `{artifact_id: str}`
   - `GET /api/v1/companies/{company_id}/artifacts/{artifact_id}` — для фронта
     - Авторизация: `CompanyViewerDep` или `CompanyAdminDep`
     - **Валидация:** Проверить, что `artifact_id` содержит `company_{company_id}/` в начале пути
     - Если не совпадает → 403 Forbidden
     - Использует `S3Client.download_file(artifact_id)` → возвращает bytes
     - Возвращает файл с правильными headers (Content-Type из S3 metadata или по расширению)
   - `GET /api/v1/internal/artifacts/{artifact_id}` — для Sales-Agent
     - Авторизация: `X-Service-Key` (через `require_service_api_key`)
     - Использует `S3Client.download_file(artifact_id)` → возвращает bytes
     - Возвращает файл (application/octet-stream или правильный Content-Type)
   - `GET /api/v1/internal/messages/{message_id}` — получение сообщения (для проверки транскрипции)
     - Авторизация: `X-Service-Key`
     - Использует `ChatService.get_message_by_id(message_id)` или `messages_repo.get_by_message_id()`
     - Возвращает `ChatMessageResponse` с `content` (содержит транскрипцию, если уже выполнена)
   - `POST /api/v1/internal/messages/{message_id}/transcription` — уведомление о транскрипции
     - Авторизация: `X-Service-Key`
     - Принимает `{transcribed_text: str}`
     - Использует `ChatService.get_message_by_id()` → обновляет `content` транскрипцией → `await message.save()`
     - Логирование успешного сохранения

3. **S3Client:**
   - Метод `upload_file()` уже возвращает S3 key (используется как artifact_id)
   - Метод `download_file()` принимает S3 key напрямую

### Phase 2: Common Library Audio Conversion Service

5. **Создать AudioConversionService в common-lib:**
   - Расположение: `libs/common/src/common/services/audio_converter.py` (создать директорию `services/` если её нет)
   - Класс `AudioConversionService` с методом `convert_to_mp3(audio_bytes: bytes, input_format: str | None = None, timeout_s: float = 60.0) -> bytes`
   - Использует ffmpeg для конвертации любого аудио формата в mp3
   - Параметры конвертации: моно, 44.1kHz (или другой стандартный формат для голосовых)
   - Обработка ошибок и таймаутов
   - Логирование процесса конвертации через structlog
   - Зависимость: ffmpeg должен быть доступен в системе (коннекторы должны иметь ffmpeg)
   - Экспорт через `libs/common/src/common/__init__.py` для удобного импорта

### Phase 3: Schema Updates

6. **Обновить InboundEnvelope:**
   - Добавить поле `artifact_ids: list[str] = Field(default_factory=list)`
   - Убрать поле `audio: AudioData | None` (больше не используется)
   - Обновить документацию

7. **Обновить InternalInboundRequest:**
   - Уже содержит `envelope: InboundEnvelope`, поэтому `artifact_ids` автоматически передаются

8. **Обновить ChatMessage schemas (API responses):**
   - Добавить `artifact_ids: list[str]` в `ChatMessageResponse`
   - Поле `content` уже существует и будет использоваться для транскрипции
   - Обновить маппинг из модели в схему

### Phase 4: Backend Message Handling

9. **Обновить endpoint `/inbound`:**
   - При получении `InboundEnvelope` с `artifact_ids`:
     - Сохранить `artifact_ids` в `ChatMessage.artifact_ids` (JSONField как список строк)
     - Определить `ChatMessage.type` на основе `artifact_ids`:
       - Парсить S3 key из `artifact_id` (формат: `company_{id}/{file_type}/{file_id}.{ext}`)
       - Если `file_type` в пути == `voice` или `audio` → `ChatMessageType.AUDIO`
       - Если `file_type` == `image` → `ChatMessageType.IMAGE`
       - Если `file_type` == `video` → `ChatMessageType.VIDEO`
       - Иначе → `ChatMessageType.TEXT` (по умолчанию)
     - НЕ проверять валидность `artifact_id` (доверяем коннектору)
   - **Обновить `ChatService.create_message()`:** добавить параметр `artifact_ids: list[str] | None = None`
   - **Обновить `ChatRepository.create_message()`:** добавить параметр `artifact_ids: list | None = None` и сохранять в модель

10. **Обновить форвардинг в Sales-Agent:**
    - `InternalInboundRequest` уже содержит `envelope` с `artifact_ids`
    - Убедиться, что `artifact_ids` корректно передаются в Sales-Agent

11. **Endpoint для транскрипции:**
    - `POST /api/v1/internal/messages/{message_id}/transcription`
    - Принимает `{transcribed_text: str}`
    - Использовать `ChatService.get_message_by_id(message_id)` для получения сообщения
    - Обновить `ChatMessage.content` транскрипцией через `ChatRepository.update()` или прямой `await message.save()`
    - Логирование успешного сохранения

### Phase 5: Telegram Module (первый коннектор)

12. **Создать BackendArtifactClient:**
    - Клиент для загрузки файлов в Backend
    - Метод `upload_file(file_bytes, filename, file_type, company_id, connector_id)` → возвращает `artifact_id`
    - Использует `X-Service-Key` и `X-Connector-Id` для авторизации
    - Обработка ошибок и retry логика

13. **Обновить обработку голосовых:**
    - Скачать голосовое через Telegram Bot API
    - Конвертировать в mp3 через `AudioConversionService.convert_to_mp3()` из common-lib
    - Загрузить в Backend через `BackendArtifactClient.upload_file()`
    - Получить `artifact_id` → добавить в `InboundEnvelope.artifact_ids`
    - Убрать передачу `bytes_base64` через `audio` поле

14. **Обновить обработку audio сообщений:**
    - Аналогично голосовым: скачать → конвертировать в mp3 → загрузить → получить `artifact_id`

### Phase 6: Sales-Agent Integration

15. **Создать BackendArtifactClient в Sales-Agent:**
    - Клиент для запроса файлов по `artifact_id`
    - Метод `download_artifact(artifact_id)` → возвращает `bytes`
    - Использует `X-Service-Key` для авторизации
    - Обработка ошибок

16. **Обновить обработку вложений:**
    - При получении `InternalInboundRequest` с `artifact_ids`:
      - Запросить у Backend информацию о сообщении через `GET /api/v1/internal/messages/{message_id}` для проверки `content`
      - Если `content` уже есть и не пустое → использовать кеш, пропустить транскрипцию
      - Иначе → запросить файл у Backend через `BackendArtifactClient.download_artifact()`
      - Транскрибировать → уведомить Backend о транскрипции через endpoint (обновляет `content`)

17. **Обновить транскрипцию:**
    - Работать с файлами из Backend вместо base64
    - Файлы уже в mp3 формате (конвертированы коннекторами), можно транскрибировать напрямую
    - После транскрипции вызывать `POST /api/v1/internal/messages/{message_id}/transcription`
    - Обработка ошибок при сохранении транскрипции

18. **Обновить маппинг InternalInboundRequest → IncomingMessage:**
    - Извлекать `artifact_ids` из `envelope.artifact_ids`
    - Добавлять в `IncomingMessage.attachments` как структурированные объекты:
      - Парсить путь из `artifact_id` для определения `type` (voice/audio → "audio", image → "image", video → "video")
      - Определить `mime` из расширения файла
      - Формат: `{"type": "audio", "artifact_id": artifact_id, "mime": "audio/mpeg"}`
    - Убрать обработку `envelope.audio` (больше не используется)
    - Обновить `map_to_incoming_message()` в `apps/sales-agent/src/sales_agent/api/internal_utils.py`

### Phase 7: Model-Level Abstractions

19. **Методы в ChatMessage:**
    - Добавить `async def download_artifact(artifact_id: str, artifact_service: ArtifactService) -> bytes`
    - Использует `ArtifactService` для скачивания
    - Обработка ошибок

### Phase 8: Wappi Module
2
20. **Обновить обработку голосовых (аналогично Telegram):**
    - Скачать → конвертировать в mp3 → загрузить в Backend
    - Использовать `artifact_ids` вместо base64
    - Обновить `WappiTelegramHandler` и `WappiWhatsAppHandler`

## Contract Changes

### Connector → Backend (NEW)

**Pre-processing endpoint:**
```
POST /api/v1/internal/artifacts/upload
Content-Type: multipart/form-data
X-Service-Key: {shared_service_key}
X-Connector-Id: {connector_id}

Form data:
  - file: File (required)
  - file_type: str (required, one of: voice, audio, image, video, document)
  - company_id: int (required)
```

**Response:**
```json
{
  "artifact_id": "company_123/voice/abc123def456.mp3"
}
```

### Connector → Backend (UPDATED)

**Inbound message:**
```
POST /api/v1/messages/inbound
Content-Type: application/json
X-Service-Key: {shared_service_key}
X-Connector-Id: {connector_id}

{
  "conversation_id": "...",
  "user_id": "...",
  "text": "...",
  "artifact_ids": ["company_123/voice/abc123def456.mp3"],  // NEW
  "ts": 1234567890.0,
  ...
}
```

### Sales-Agent → Backend (NEW)

**Download artifact:**
```
GET /api/v1/internal/artifacts/{artifact_id}
X-Service-Key: {shared_service_key}

Response: File content (application/octet-stream)
```

**Save transcription:**
```
POST /api/v1/internal/messages/{message_id}/transcription
Content-Type: application/json
X-Service-Key: {shared_service_key}

{
  "transcribed_text": "Transcribed text here"
}
```

## Schema Changes Required

### `InboundEnvelope` (libs/common/src/common/models/inbound.py)

```python
class InboundEnvelope(BaseModel):
    conversation_id: str
    user_id: str
    text: str | None = None
    ts: float
    artifact_ids: list[str] = Field(default_factory=list)  # NEW: list of S3 artifact IDs
    message_id: str | None = None
    role: MessageRole = MessageRole.USER
    is_historical: bool = False
    sender_name: str | None = None
    sender_username: str | None = None
    sender_phone: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)
```

**Note:** Поле `audio: AudioData | None` удаляется, так как больше не используется.

### `ChatMessage` (apps/backend/src/backend/modules/chat/models.py)

```python
class ChatMessageType(str, Enum):
    TEXT = "text"
    AUDIO = "audio"  # NEW
    IMAGE = "image"  # NEW
    VIDEO = "video"  # NEW
    INTERNAL_NOTE = "internal_note"
    SYSTEM_EVENT = "system_event"

class ChatMessage(BaseModel):
    ...
    type = fields.CharEnumField(ChatMessageType, max_length=16, default=ChatMessageType.TEXT)
    content = fields.TextField()  # Existing field: used for text content and transcription
    attachments = fields.JSONField(default=list)  # Existing field, kept for compatibility
    artifact_ids = fields.JSONField(default=list)  # NEW: list[str] of S3 keys, stored as JSONB array in PostgreSQL
    ...
```

### `ChatMessageResponse` (apps/backend/src/backend/modules/chat/schemas.py)

```python
class ChatMessageResponse(ChatMessageBase):
    ...
    artifact_ids: list[str] = Field(default_factory=list)  # NEW
    # content field already exists and will contain transcription for audio messages
    ...
```

## Risks / Open Questions

1. **Миграция коннекторов:**
   - Telegram и Wappi модули должны быть обновлены одновременно
   - Все коннекторы переходят на новый формат без fallback

2. **Конвертация файлов:**
   - Конвертация в mp3 происходит в коннекторах перед загрузкой в S3 через `AudioConversionService`
   - Backend ожидает только mp3 формат
   - Требование: ffmpeg должен быть доступен в коннекторах

3. **Размер файлов:**
   - Ограничение: 50MB (валидация в pre-processing endpoint)
   - Настроить лимиты FastAPI multipart при необходимости

4. **Миграция существующих данных:**
   - Текущие сообщения с `attachments` остаются как есть
   - Новые сообщения используют `artifact_ids`

## Rollback Strategy

1. **Откат изменений в коннекторах:**
   - Вернуть передачу base64 (но нужно будет восстановить поле `audio` в `InboundEnvelope`)
   - Обновить обработку в коннекторах

2. **Откат изменений в Backend:**
   - Endpoints остаются, но не используются
   - Новое поле `artifact_ids` nullable, не ломает существующий функционал
   - Поле `content` используется как раньше

3. **Откат изменений в Sales-Agent:**
   - Вернуть работу с base64 (но нужно будет восстановить поле `audio` в `InboundEnvelope`)
   - Убрать запросы к Backend для скачивания файлов

4. **Миграции БД:**
   - Новое поле `artifact_ids` nullable, не ломает существующий функционал
   - Поле `content` уже существует, изменения не требуются
   - Можно создать миграцию для отката (если требуется)

## Success Criteria

- ✅ Коннекторы загружают файлы в S3 через pre-processing endpoint
- ✅ Backend сохраняет `artifact_ids` в сообщениях
- ✅ Sales-Agent запрашивает файлы по `artifact_id` и транскрибирует
- ✅ Транскрипции кешируются в Backend (в поле `content`)
- ✅ Фронт может получать оригинальные файлы по `artifact_id`
- ✅ Абстракция на уровне модели работает (`message.download_artifact()`)
- ✅ Telegram и Wappi модули поддерживают новый формат

## Implementation Order

1. **Backend Infrastructure** (Phase 1) — основа для всего остального
2. **Common Library Audio Service** (Phase 2) — сервис конвертации для переиспользования коннекторами
3. **Schema Updates** (Phase 3) — обновление контрактов
4. **Backend Message Handling** (Phase 4) — обработка artifact_ids
5. **Telegram Module** (Phase 5) — первый коннектор, проще для тестирования
6. **Sales-Agent Integration** (Phase 6) — обработка и транскрипция
7. **Model Abstractions** (Phase 7) — удобные утилиты
8. **Wappi Module** (Phase 8) — второй коннектор

**Примечание:** AudioConversionService должен быть создан до обновления коннекторов. Bitrix-module не затрагивается в этом плане.

