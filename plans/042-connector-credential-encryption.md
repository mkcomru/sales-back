# 042 — Connector Credential Encryption

## Objective

Зашифровать чувствительные поля в `Connector.config` (bot_token, wappi_token, wazzup_api_key, webhook_secret) с использованием существующей инфраструктуры `EnvelopeEncryption`. Хранение — внутри текущего `config` JSONField, без новых колонок. Одноразовый скрипт миграции для существующих строк.

## Зачем это делаем

- **Проблема:** `Connector.config` хранится как plaintext JSON в PostgreSQL. Любой, у кого есть прямой доступ к базе (бэкап, дамп, утечка), видит все токены ботов и API-ключи в открытом виде.
- **Ценность:** Шифрование credentials на уровне хранилища — стандартная практика безопасности. Компрометация базы не означает компрометацию интеграций с мессенджерами.
- **Что станет возможным:** Соответствие требованиям безопасности при аудитах и подключении корпоративных клиентов. Инфраструктура уже используется для `integrations` — унификация подхода по всему проекту.

## Context

### Что шифруем

| Тип коннектора | Секретные поля (шифруются) | Несекретные поля (plaintext) |
|---|---|---|
| `TELEGRAM` | `bot_token`, `webhook_secret` | `webhook_path` |
| `WAPPI` | `wappi_token` | `wappi_profile_id` |
| `WAZZUP` | `wazzup_api_key` | `channel_id` |
| `CUSTOM` | нет | `transport_endpoint` |

### Формат хранения в `config`

Секретные поля заменяются на сериализованный `EncryptedPayload` прямо внутри того же JSON-объекта:

```json
{
  "bot_token": {"encrypted_data": "...", "encrypted_dek": "..."},
  "webhook_secret": {"encrypted_data": "...", "encrypted_dek": "..."},
  "webhook_path": "/webhook/abc123"
}
```

Несекретные поля остаются как строки. По ключу можно определить, зашифровано ли поле (dict с `encrypted_data`/`encrypted_dek` vs строка).

### Существующая инфраструктура

- `libs/common/src/common/crypto.py` — `EnvelopeEncryption`, `EncryptedPayload`
- `libs/common/src/common/config.py` — `ENCRYPTION__MASTER_KEY` env var
- `apps/backend/src/backend/modules/integrations/service.py` — образец `_encrypt_credentials()` / `_decrypt_credentials()`

### Ключевые файлы

- `apps/backend/src/backend/modules/transport/models.py` — модель `Connector`
- `apps/backend/src/backend/modules/transport/schemas.py` — `TelegramConnectorConfig`, `WappiConnectorConfig`, `WazzupConnectorConfig`
- `apps/backend/src/backend/modules/transport/service.py` — `ConnectorsService`
- `apps/backend/src/backend/modules/transport/repository.py` — `ConnectorsRepository`

## Design

### Нет изменений схемы БД

`Connector.config` остаётся JSONField. Миграция Aerich не нужна.

### Маппинг секретных полей по типу коннектора

```python
SENSITIVE_FIELDS: dict[ConnectorType, frozenset[str]] = {
    ConnectorType.TELEGRAM: frozenset({"bot_token", "webhook_secret"}),
    ConnectorType.WAPPI: frozenset({"wappi_token"}),
    ConnectorType.WAZZUP: frozenset({"wazzup_api_key"}),
    ConnectorType.CUSTOM: frozenset(),
}
```

### API-контракт

- **Входящие запросы** (create/update): принимают plaintext config — секретные поля шифруются в сервисе перед записью в БД.
- **Ответы наружу** (`ConnectorResponse`): секретные поля **не возвращаются** (убираются из config при сериализации).
- **Внутренние запросы** от транспортных модулей (`GET /transport/connectors/{id}` с `X-Service-Key`): config расшифровывается и возвращается в полном plaintext виде — иначе модули сломаются.

## Plan

### Step 1 — Сервис: encrypt/decrypt внутри config

В `apps/backend/src/backend/modules/transport/service.py`:

- `_get_encryption() -> EnvelopeEncryption` — получить из `settings.encryption.master_key`, кинуть исключение если не задан
- `_encrypt_config(connector_type: ConnectorType, config: dict) -> dict` — пройти по `SENSITIVE_FIELDS[connector_type]`, для каждого присутствующего поля зашифровать значение через `EnvelopeEncryption`, заменить строку на `EncryptedPayload.model_dump()`
- `_decrypt_config(connector_type: ConnectorType, config: dict) -> dict` — пройти по `SENSITIVE_FIELDS[connector_type]`, для каждого поля, если значение — dict с `encrypted_data`/`encrypted_dek`, расшифровать обратно в строку
- `_strip_credentials(connector_type: ConnectorType, config: dict) -> dict` — вернуть копию config без секретных полей (для внешних ответов)

Обновить:
- `create_connector()` — вызвать `_encrypt_config()` перед передачей в репозиторий
- `update_connector()` — аналогично, если `config` обновляется
- Добавить метод `get_connector_decrypted(connector_id: str) -> ConnectorWithConfig` для внутренних запросов (расшифрованный config)

### Step 2 — Router: разграничить внешний и внутренний ответ

В `apps/backend/src/backend/modules/transport/routers.py`:

- `GET /transport/connectors/{id}` с `X-Service-Key` (транспортные модули) → вызвать `get_connector_decrypted()`, вернуть полный plaintext config
- `GET /transport/connectors` / `GET /transport/connectors/{id}` с обычным auth → вызвать `_strip_credentials()`, вернуть config без секретных полей
- `PATCH /transport/connectors/{id}` — принимает plaintext config, в сервисе шифруется

Проверить: тот же endpoint используется разными клиентами, или разные? Если один — различать по типу auth-токена.

### Step 3 — Скрипт миграции существующих данных

Написать `apps/backend/src/backend/scripts/encrypt_connector_credentials.py`:

```bash
uv run python -m backend.scripts.encrypt_connector_credentials
```

Логика:
1. Загрузить все `Connector` где `config != {}`
2. Для каждого — проверить, зашифрованы ли уже секретные поля (если значение — dict, пропустить)
3. Вызвать `_encrypt_config()` → сохранить обновлённый `config`
4. Логировать каждую запись (ID, тип, успех/ошибка)

Скрипт идемпотентен: повторный запуск не ломает уже зашифрованные записи.

### Step 4 — Проверка

- Создать коннектор через API → убедиться что в БД `config.bot_token` — dict с `encrypted_data`, а не строка
- Получить коннектор через внешний API → убедиться что `bot_token` отсутствует в ответе
- Получить коннектор через внутренний endpoint (с `X-Service-Key`) → убедиться что `bot_token` — plaintext строка
- Запустить транспортный модуль → убедиться что он корректно получает credentials и бот работает

## Constraints

- `ENCRYPTION__MASTER_KEY` должен быть задан в `.env.shared` до запуска
- Скрипт миграции данных запускать до деплоя нового кода (или как часть деплоя до старта сервиса)
- Транспортные модули продолжают работать без изменений кода — получают plaintext от backend через существующий endpoint
- Custom-коннекторы (`SENSITIVE_FIELDS` пустой) — config не меняется, шифровать нечего
