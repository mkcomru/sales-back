# ENV: переменные окружения проекта

Источник истины — `libs/common/src/common/config.py`. Для Docker-запуска дополнительно смотри `docker-compose.yml`.

Секреты в репозиторий не коммитить.

## 1. Кто какие env-файлы читает

### Docker Compose

Compose использует **жёстко прописанные файлы**:

| Сервис | Файлы | Что использует |
|---|---|---|
| `backend` | `.env.shared.dev`, `apps/backend/.env` | PostgreSQL, Redis, S3, auth, transport URLs, sales-agent URL |
| `backend-migrations` | `.env.shared.dev`, `apps/backend/.env` | PostgreSQL; S3 и auth нужны для валидации настроек |
| `worker-hub` | `.env.shared.dev`, `apps/backend/.env` | PostgreSQL, sales-agent, transport URLs, `WORKERS` |
| `sales-agent` | `.env.shared.dev`, `apps/sales-agent/.env` | LLM, backend, Redis, S3 (валидация), RAG, FAQ, audio, Langfuse |
| `telegram-module` | `.env.shared.dev`, `apps/telegram-module/.env` | Backend, Telegram API, Redis, S3 (валидация) |
| `wappi-module` | `.env.shared.dev`, `apps/wappi-module/.env` | Backend, Wappi API, Redis, S3 (валидация) |
| `wazzup-module` | `.env.shared.dev`, `apps/wazzup-module/.env` | Backend, Wazzup API, Redis, S3 (валидация) |
| `minio` | `.env.shared.dev` | `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD` |
| `redis` | — | Пароль не настроен |
| `traefik` | `.env.shared.dev` | `DOMAIN_*`; `ACME_EMAIL` для Compose-интерполяции берётся из корневого `.env` |

Важно:

- `.env.shared.dev` и `apps/<service>/.env` должны существовать: если файла нет, Compose завершится ошибкой.
- Корневой `.env` **не передаётся приложению**. Он нужен Compose для подстановок вида `${ACME_EMAIL}`.
- `env_file` не участвует в Compose-интерполяции. Переменные из `.env.shared.dev` не подставятся в `${...}` автоматически.
- `backend-migrations` и `worker-hub` используют env backend, а не отдельные файлы.

### Нативный запуск

Pydantic-settings читает:

1. `.env.shared` — базовые значения;
2. `.env.shared.<environment>` — переопределения;
3. `apps/<service>/.env` — значения сервиса;
4. `apps/<service>/.env.<environment>` — переопределения сервиса.

Если `APP__ENVIRONMENT` или `ENV` задан явно, базовые файлы не используются: только env-специфичные.

`just dev` дополнительно делает `source .env.shared.dev` и переопределяет URL на `localhost`.

### Именование

Двойное подчёркивание означает вложенность:

```env
DATABASE__URL=...        # settings.database.url
LLM__API_KEY=...         # settings.llm.api_key
EVENTING__STREAM__NAME=... # settings.eventing.stream.name
```

Для части модулей есть плоские алиасы: `TELEGRAM_MODULE_*`, `WAPPI_MODULE_*`, `WAZZUP_MODULE_*`.

## 2. Куда сервисы ходят за данными

| Сервис | Источники данных |
|---|---|
| `backend` | PostgreSQL, Redis, S3/MinIO, `sales-agent`, transport-модули |
| `backend-migrations` | только PostgreSQL |
| `worker-hub` | PostgreSQL, `sales-agent`, transport-модули |
| `sales-agent` | `backend`, LLM API, Redis, Qdrant, embedding/reranker API, Langfuse |
| `telegram-module` | `backend`, Telegram Bot API, Redis; S3 — через backend |
| `wappi-module` | `backend`, Wappi API, Redis; S3 — через backend |
| `wazzup-module` | `backend`, Wazzup API, Redis; S3 — через backend |
| `minio` | локальный диск |
| `redis` | память/диск |

`backend` — единственный сервис, который работает с БД напрямую. `sales-agent` и transport-модули stateless.

## 3. Общие настройки

Эти переменные есть в общей модели и потенциально доступны всем Python-сервисам.

### Приложение, БД, Redis, сервисная авторизация

| Переменная | По умолчанию | Обязательность | Описание |
|---|---:|---|---|
| `APP__DEBUG` | `false` | опционально | Debug-режим и подробные логи |
| `APP__VERSION` | `0.1.0` | опционально | Версия приложения |
| `APP__ENVIRONMENT` | `dev` | опционально | Окружение: `dev`, `staging`, `prod` |
| `ENV` | — | опционально | Только выбор env-файлов; не поле настроек |
| `APP_ENV` | — | опционально | То же, что `ENV` |
| `DATABASE__URL` | нет | нужен backend | PostgreSQL URL |
| `REDIS__URL` | нет | нужен при eventing | Redis URL |
| `SERVICE__API_KEY` | нет | нужен для межсервисных вызовов | Общий ключ сервисов |
| `SERVICE__HEADER` | `X-Service-Key` | опционально | HTTP-заголовок для ключа |
| `BACKEND__URL` | нет | нужен sales-agent и transport-модулям | Backend API, включая `/api/v1` |
| `SALES_AGENT__URL` | нет | нужен backend | Sales-agent API, без `/api/v1` |

`DATABASE__URL` должен содержать host, port, user, password и database. Пример:

```env
DATABASE__URL=postgresql://postgres:password@postgres:5432/sales_bot
```

Для Docker не использовать `localhost`: это будет сам контейнер. Для native-режима — `localhost`.

`BACKEND__URL` для контейнеров:

```env
BACKEND__URL=http://backend:8000/api/v1
```

`SALES_AGENT__URL` для backend:

```env
SALES_AGENT__URL=http://sales-agent:8000
```

### CORS

| Переменная | По умолчанию | Описание |
|---|---:|---|
| `CORS__ALLOW_ORIGINS` | `[]` | Разрешённые origins; пусто = CORS выключен |
| `CORS__ALLOW_METHODS` | `["*"]` | Разрешённые методы |
| `CORS__ALLOW_HEADERS` | `["*"]` | Разрешённые заголовки |
| `CORS__EXPOSE_HEADERS` | `[]` | Заголовки, доступные браузеру |
| `CORS__ALLOW_CREDENTIALS` | `false` | Разрешить credentials |
| `CORS__MAX_AGE` | `600` | Время кеширования preflight, сек |

Списки можно задавать JSON-массивом или через запятую.

Ошибочное имя: `CORS__ORIGINS` — **не читается**. Используй `CORS__ALLOW_ORIGINS`.

### Eventing / Redis Streams

| Переменная | По умолчанию | Обязательность | Описание |
|---|---:|---|---|
| `EVENTING__ENABLED` | `false` | опционально | Включить event bus |
| `EVENTING__BROKER` | `redis_streams` | опционально | Пока поддерживается только Redis Streams |
| `EVENTING__STREAM__NAME` | `backend.events` | опционально | Имя потока |
| `EVENTING__STREAM__GROUP` | пусто | нужен при eventing | Consumer group, уникальная для сервиса |
| `EVENTING__STREAM__CONSUMER_NAME` | hostname | опционально | Имя consumer; по умолчанию hostname |
| `EVENTING__STREAM__BLOCK_MS` | `5000` | опционально | Block timeout чтения, мс |
| `EVENTING__STREAM__COUNT` | `10` | опционально | Размер пачки чтения |

Если `EVENTING__ENABLED=true`, обязательно нужны `REDIS__URL` и `EVENTING__STREAM__GROUP`. Иначе приложение упадёт при старте.

### S3 / MinIO

| Переменная | По умолчанию | Обязательность | Описание |
|---|---:|---|---|
| `S3__ENDPOINT_URL` | нет | **обязательно** | URL S3/MinIO |
| `S3__ACCESS_KEY_ID` | нет | **обязательно** | Access key |
| `S3__SECRET_ACCESS_KEY` | нет | **обязательно** | Secret key |
| `S3__BUCKET_NAME` | нет | **обязательно** | Bucket с медиа |
| `S3__REGION_NAME` | `null` | опционально | Регион; клиент использует `us-east-1`, если пусто |
| `S3__USE_SSL` | `false` | опционально | TLS для S3-клиента |

Все четыре обязательных S3-поля проверяются при создании настроек **любым Python-сервисом**, даже если сервис сам S3 не использует. Поэтому они должны быть в env backend, migrations, worker, sales-agent и всех transport-модулей.

`S3__ENDPOINT_URL` попадает в presigned URL. Нельзя ставить `http://minio:9000`, если ссылки должны открываться в браузере или на другом сервере: используй публичный домен или публичный IP.

Bucket `S3__BUCKET_NAME` сам не создаётся.

### Загрузка артефактов и шифрование

| Переменная | По умолчанию | Обязательность | Описание |
|---|---:|---|---|
| `ARTIFACT_UPLOAD__MAX_RETRIES` | `3` | опционально | Количество попыток загрузки |
| `ARTIFACT_UPLOAD__RETRY_DELAY_S` | `1.0` | опционально | Базовая задержка между попытками |
| `ENCRYPTION__MASTER_KEY` | нет | нужен для коннекторов | Ключ шифрования credentials |

`ENCRYPTION__MASTER_KEY` нужен backend при создании/чтении секретов коннекторов и интеграций. Без него эти операции падают с ошибкой.

## 4. Backend

Дополнительно к общим настройкам.

### Auth

| Переменная | По умолчанию | Обязательность | Описание |
|---|---:|---|---|
| `AUTH__JWT_SECRET_KEY` | нет | **обязательно** | Секрет подписи JWT |
| `AUTH__JWT_ALGORITHM` | `HS256` | опционально | Алгоритм JWT |
| `AUTH__ACCESS_TOKEN_EXPIRE_MINUTES` | `15` | опционально | Время жизни access token |
| `AUTH__REFRESH_TOKEN_EXPIRE_DAYS` | `30` | опционально | Время жизни refresh token |

`AUTH__JWT_SECRET_KEY` фактически нужен также `backend-migrations` и `worker-hub`, потому что они создают те же настройки.

### Transport URLs

| Переменная | По умолчанию | Описание |
|---|---:|---|
| `TRANSPORT__TELEGRAM__URL` | нет | Базовый URL telegram-module |
| `TRANSPORT__TELEGRAM__RELOAD_URL` | нет | URL принудительной перезагрузки telegram-ботов |
| `TRANSPORT__WAPPI__URL` | нет | Базовый URL wappi-module |
| `TRANSPORT__WAZZUP__URL` | нет | Базовый URL wazzup-module |

Значения нужны для исходящей доставки сообщений. Без них соответствующий транспорт не сможет отправить ответ.

Пример для Docker:

```env
TRANSPORT__TELEGRAM__URL=http://telegram-module:8000
TRANSPORT__WAPPI__URL=http://wappi-module:8000
TRANSPORT__WAZZUP__URL=http://wazzup-module:8000
```

### Sentry

| Переменная | По умолчанию | Описание |
|---|---:|---|
| `SENTRY__DSN` | нет | DSN; пусто = Sentry выключен |
| `SENTRY__SEND_DEFAULT_PII` | `true` | Отправлять PII |
| `SENTRY__TRACES_SAMPLE_RATE` | `0.5` | Доля трейсов |
| `SENTRY__ENVIRONMENT` | `null` | Окружение; fallback — `APP__ENVIRONMENT` |

### Worker runtime

| Переменная | По умолчанию | Описание |
|---|---:|---|
| `WORKERS` | `all` | Какие воркеры запускать |

Допустимые значения: `all`, `task_scheduler`, `ping_evaluator`, либо список через запятую.

## 5. Sales-agent

### LLM и legacy bot

| Переменная | По умолчанию | Обязательность | Описание |
|---|---:|---|---|
| `LLM__BASE_URL` | `https://api.openai.com/v1` | опционально | OpenAI-совместимый endpoint |
| `LLM__API_KEY` | нет | **нужен для старта** | Ключ LLM |
| `LLM__LIGHT_MODEL` | `gpt-4o-mini` | опционально | Модель для лёгких задач |
| `LLM__LARGE_MODEL` | `gpt-4o` | опционально | Основная модель |
| `BOT__TOKEN` | нет | опционально | Legacy-токен, текущим pipeline не используется |

Без `LLM__API_KEY` sales-agent падает при создании LLM-клиента.

### Langfuse

| Переменная | По умолчанию | Описание |
|---|---:|---|
| `LANGFUSE__ENABLED` | `false` | Включить телеметрию |
| `LANGFUSE__PUBLIC_KEY` | нет | Public key |
| `LANGFUSE__SECRET_KEY` | нет | Secret key |
| `LANGFUSE__HOST` | нет | URL Langfuse |
| `LANGFUSE__SAMPLE_RATE` | `1.0` | Доля трейсов |
| `LANGFUSE__ENABLE_GENERATION_CALLBACK_ONLY` | `true` | Только generation callbacks |

Ошибочное имя: `LANGFUSE__BASE_URL` — **не читается**. Используй `LANGFUSE__HOST`.

### Debounce и коннекторы

| Переменная | По умолчанию | Описание |
|---|---:|---|
| `DEBOUNCE__WINDOW_SECONDS` | `45` | Окно склейки сообщений, сек |
| `DEBOUNCE__PER_CHANNEL` | `{}` | Переопределения по каналу, JSON-объект |
| `CONNECTORS_REFRESH_INTERVAL_S` | `1800` | Период обновления коннекторов из backend, сек |
| `TRANSPORT__TELEGRAM__ENDPOINT` | нет | Поле есть в настройках, но текущий outbound идёт через backend |

`CONNECTORS_REFRESH_INTERVAL_S=0` отключает периодическое обновление.

### RAG

| Переменная | По умолчанию | Описание |
|---|---:|---|
| `RAG__ENABLED` | `true` | Включить RAG |
| `RAG__DEFAULT_KB` | `default` | База знаний по умолчанию |
| `RAG__EMBEDDING__BASE_URL` | нет | Embedding API |
| `RAG__EMBEDDING__API_KEY` | нет | Ключ embedding API |
| `RAG__EMBEDDING__MODEL` | `BAAI/bge-m3` | Модель эмбеддингов |
| `RAG__EMBEDDING__DIMENSION` | `1024` | Размерность вектора |
| `RAG__EMBEDDING__TIMEOUT_S` | `30.0` | Таймаут embedding API |
| `RAG__QDRANT__URL` | нет | URL Qdrant |
| `RAG__QDRANT__API_KEY` | нет | Ключ Qdrant |
| `RAG__QDRANT__COLLECTION_PREFIX` | `kb` | Префикс коллекций |
| `RAG__QDRANT__PREFER_SPARSE` | `false` | Предпочитать sparse-векторы |
| `RAG__RERANKER__ENABLED` | `false` | Включить reranker |
| `RAG__RERANKER__API_KEY` | нет | Ключ reranker API |
| `RAG__RERANKER__MODEL` | пусто | Модель reranker |
| `RAG__RERANKER__TIMEOUT_S` | `30.0` | Таймаут reranker |
| `RAG__CHUNK_MAX_TOKENS` | `800` | Максимум токенов в чанке |
| `RAG__CHUNK_OVERLAP_TOKENS` | `120` | Перекрытие чанков |

При `RAG__ENABLED=true` нужны рабочие embedding и Qdrant. `RAG__RERANKER__BASE_URL` не существует.

### FAQ, humanizer

| Переменная | По умолчанию | Описание |
|---|---:|---|
| `FAQ__ENABLED` | `true` | Включить FAQ |
| `FAQ__THRESHOLD` | `0.82` | Порог совпадения |
| `FAQ__PATH` | нет | Путь к FAQ-файлу |
| `FAQ__USE_QDRANT` | `false` | Искать FAQ в Qdrant |
| `FAQ__KB_NAME` | `faq` | Имя FAQ-базы |
| `HUMANIZER__ENABLED` | `true` | Включить humanizer |

Ошибочное имя: `FAQ__MATCH_THRESHOLD` — **не читается**. Используй `FAQ__THRESHOLD`.

### Audio / transcription

| Переменная | По умолчанию | Описание |
|---|---:|---|
| `AUDIO__MODEL` | `gpt-4o-mini-transcribe` | Модель транскрипции |
| `AUDIO__BASE_URL` | нет | Endpoint транскрипции |
| `AUDIO__API_KEY` | нет | Ключ транскрипции |
| `AUDIO__MAX_AUDIO_BYTES` | `15000000` | Максимальный размер аудио |
| `AUDIO__SUPPORTED_MIMES` | `["audio/ogg","audio/opus","audio/mpeg"]` | Поддерживаемые MIME |
| `AUDIO__TIMEOUT_S` | `60.0` | Таймаут запроса |
| `AUDIO__TRANSCODE_ENABLED` | `true` | Перекодировать перед отправкой |
| `AUDIO__FFMPEG_PATH` | `ffmpeg` | Путь к ffmpeg |

Без `AUDIO__API_KEY` транскрипция падает при попытке использования. `AUDIO__TRANSCRIBE__*` не читаются; используй `AUDIO__*`.

### Другие сервисы

| Переменная | По умолчанию | Описание |
|---|---:|---|
| `YANDEX__TOKEN` | нет | Токен Yandex |

## 6. Telegram-module

| Переменная | По умолчанию | Обязательность | Описание |
|---|---:|---|---|
| `TELEGRAM_MODULE_PUBLIC_URL` | нет | опционально | Публичный URL модуля для webhook |
| `DEFAULT_MODE` | `polling` | опционально | Допустимо только `polling` |
| `BACKEND_BOTS_PATH` | `/transport/telegram/bots` | опционально | Путь API backend для ботов |
| `TELEGRAM_MODULE_REQUEST_TIMEOUT_S` | `100.0` | опционально | Таймаут запросов |
| `TELEGRAM_MODULE_CONFIG_REFRESH_INTERVAL_S` | `120.0` | опционально | Период обновления конфигурации |
| `TELEGRAM_MODULE_SIGNATURE_TOLERANCE_S` | `300` | опционально | Допуск подписи |
| `TELEGRAM_MODULE_MAX_DELIVERY_ATTEMPTS` | `3` | опционально | Попытки доставки |
| `TELEGRAM_MODULE_ALERT_AFTER_FAILURES` | `2` | опционально | Порог алерта |
| `TELEGRAM_MODULE_DROP_PENDING_ON_WEBHOOK_RESET` | `true` | опционально | Удалять pending при сбросе webhook |
| `TELEGRAM_MODULE_POLLING_TIMEOUT_S` | `25.0` | опционально | Long polling timeout |

Обязательны `BACKEND__URL=http://backend:8000/api/v1` и `SERVICE__API_KEY`. `REDIS__URL` нужен при `EVENTING__ENABLED=true`. `SALES_AGENT__URL` модуль напрямую не использует.

## 7. Wappi-module

| Переменная | По умолчанию | Описание |
|---|---:|---|
| `WAPPI_MODULE_REQUEST_TIMEOUT_S` | `10.0` | Таймаут запросов |
| `WAPPI_MODULE_CONFIG_REFRESH_INTERVAL_S` | `60.0` | Период обновления конфигурации |
| `WAPPI_MODULE_MAX_DELIVERY_ATTEMPTS` | `3` | Попытки доставки |
| `WAPPI_MODULE_INITIAL_SYNC_MESSAGES_LIMIT` | `50` | Лимит сообщений при первой синхронизации |
| `WAPPI_MODULE_INITIAL_SYNC_DIALOGS_LIMIT` | `50` | Лимит диалогов при первой синхронизации |
| `AUDIO__*` | см. раздел audio | Доступны через общие настройки |

Обязательны `BACKEND__URL` и `SERVICE__API_KEY`; `REDIS__URL` нужен при `EVENTING__ENABLED=true`.

## 8. Wazzup-module

| Переменная | По умолчанию | Описание |
|---|---:|---|
| `WAZZUP_MODULE_REQUEST_TIMEOUT_S` | `10.0` | Таймаут запросов |
| `WAZZUP_MODULE_CONFIG_REFRESH_INTERVAL_S` | `60.0` | Период обновления конфигурации |
| `WAZZUP_MODULE_MAX_DELIVERY_ATTEMPTS` | `3` | Попытки доставки |
| `WAZZUP_MODULE_WEBHOOK_URL` | нет | Публичный URL webhook Wazzup |

Пример:

```env
WAZZUP_MODULE_WEBHOOK_URL=https://example.com/wazzup/webhook
```

Обязательны `BACKEND__URL` и `SERVICE__API_KEY`; `REDIS__URL` нужен при `EVENTING__ENABLED=true`.

## 9. Коннекторы sales-agent

Обычно коннекторы загружаются из backend. Env-конфиг `CONNECTORS__*` нужен для статической/локальной конфигурации.

Формат:

```env
CONNECTORS__<ID>__<FIELD>
```

| Переменная | По умолчанию | Описание |
|---|---:|---|
| `CONNECTORS__<ID>__CONNECTOR_ID` | ключ `<ID>` | Публичный ID коннектора |
| `CONNECTORS__<ID>__TYPE` | `messaging` | Тип коннектора |
| `CONNECTORS__<ID>__CHANNEL_TYPE` | нет | Одиночный канал |
| `CONNECTORS__<ID>__CHANNEL_TYPES` | `[]` | Список каналов; элементы через `__0`, `__1` |
| `CONNECTORS__<ID>__ENABLED` | `true` | Включён ли коннектор |
| `CONNECTORS__<ID>__METADATA__<KEY>` | `{}` | Произвольные метаданные |
| `CONNECTORS__<ID>__DEBOUNCE__WINDOW_SECONDS` | нет | Окно debounce для коннектора |
| `CONNECTORS__<ID>__DEBOUNCE__MAX_BATCH_MESSAGES` | нет | Максимум сообщений в batch |
| `CONNECTORS__<ID>__DEBOUNCE__STORAGE_KEY_TEMPLATE` | нет | Шаблон ключа debounce |
| `CONNECTORS__<ID>__SECRETS__TOKEN` | нет | Основной секрет |
| `CONNECTORS__<ID>__SECRETS__EXTRA__<KEY>` | `{}` | Дополнительные секреты |
| `CONNECTORS__<ID>__CALLBACKS__DELIVERY_URL` | нет | Callback доставки |
| `CONNECTORS__<ID>__CALLBACKS__POLL_URL` | нет | Callback polling |
| `CONNECTORS__<ID>__CALLBACKS__PROXY_URL` | нет | Proxy callback |
| `CONNECTORS__<ID>__CALLBACKS__HANDOFF_URL` | нет | Callback handoff |
| `CONNECTORS__<ID>__TRANSPORT__ENABLED` | `false` | Включить transport push |
| `CONNECTORS__<ID>__TRANSPORT__ENDPOINT` | нет | URL transport |
| `CONNECTORS__<ID>__TRANSPORT__RETRIES__MAX_ATTEMPTS` | `3` | Попытки доставки |
| `CONNECTORS__<ID>__TRANSPORT__RETRIES__BACKOFF_SCHEDULE_MS__0` | `1000` | Задержка 1, мс |
| `CONNECTORS__<ID>__TRANSPORT__RETRIES__BACKOFF_SCHEDULE_MS__1` | `5000` | Задержка 2, мс |
| `CONNECTORS__<ID>__TRANSPORT__RETRIES__BACKOFF_SCHEDULE_MS__2` | `15000` | Задержка 3, мс |
| `CONNECTORS__<ID>__TRANSPORT__RETRIES__CONNECT_TIMEOUT_S` | `2.0` | Connect timeout |
| `CONNECTORS__<ID>__TRANSPORT__RETRIES__READ_TIMEOUT_S` | `6.0` | Read timeout |
| `CONNECTORS__<ID>__TRANSPORT__RETRIES__TOTAL_TIMEOUT_S` | `8.0` | Общий timeout |

Пример:

```env
CONNECTORS__BITRIX__TYPE=crm
CONNECTORS__BITRIX__CHANNEL_TYPES__0=bitrix
CONNECTORS__BITRIX__SECRETS__TOKEN=secret
CONNECTORS__BITRIX__CALLBACKS__DELIVERY_URL=https://example.com/callback
```

## 10. Инфраструктура и Docker

### Compose / PostgreSQL / MinIO / Traefik

| Переменная | По умолчанию | Кто использует | Описание |
|---|---:|---|---|
| `POSTGRES_USER` | — | PostgreSQL-контейнер | Пользователь БД |
| `POSTGRES_PASSWORD` | — | PostgreSQL-контейнер | Пароль БД |
| `POSTGRES_DB` | — | PostgreSQL-контейнер | Имя БД |
| `MINIO_ROOT_USER` | `minioadmin` | MinIO | Root user |
| `MINIO_ROOT_PASSWORD` | `minioadmin` | MinIO | Root password |
| `DOMAIN_BACKEND` | — | Traefik | Домен backend |
| `DOMAIN_SALES` | — | Traefik | Домен sales-agent |
| `DOMAIN_CONNECTOR_HUB` | — | Traefik | Домен connector hub |
| `ACME_EMAIL` | `admin@ai-gency.ru` | Compose/Traefik | Email Let's Encrypt |

`POSTGRES_*` не читаются приложением напрямую: backend использует только `DATABASE__URL`.
`MINIO_ROOT_*` должны совпадать с `S3__ACCESS_KEY_ID` и `S3__SECRET_ACCESS_KEY`.

`ACME_EMAIL` для `${ACME_EMAIL}` должен быть в корневом `.env` или shell. Значение в `.env.shared.dev` не подставится в Compose-интерполяцию.

### Docker build args

Это не runtime-env, а аргументы сборки:

| Аргумент | Назначение |
|---|---|
| `PACKAGE_NAME` | Workspace-пакет для `uv sync` |
| `APP_PATH` | Путь к приложению |
| `PYTHONPATH_SUFFIX` | Дополнительный путь |
| `UVICORN_MODULE_PATH` | Модуль uvicorn |
| `INSTALL_FFMPEG` | Установить ffmpeg в образ |

## 11. Частые ошибки

- `localhost` в `DATABASE__URL` или `REDIS__URL` внутри контейнера указывает на сам контейнер.
- `DATABASE__URL` без явного порта не принимается парсером.
- `BACKEND__URL` для transport-модулей должен включать `/api/v1`.
- `SALES_AGENT__URL` для backend не должен включать `/api/v1`.
- S3-переменные обязательны всем Python-сервисам, даже если они не работают с S3 напрямую.
- S3 endpoint должен быть доступен снаружи, если используются presigned URL.
- `EVENTING__STREAM__GROUP` должна быть уникальной для каждого сервиса.
- `SERVICE__API_KEY` должен совпадать во всех сервисах.
- `ENCRYPTION__MASTER_KEY` нельзя менять после сохранения секретов: старые credentials перестанут расшифровываться.
