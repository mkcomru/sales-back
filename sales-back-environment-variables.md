# Environment variables: sales-back

Справочник переменных окружения, сформированный по актуальному состоянию ветки `main` репозитория `mkcomru/sales-back` (проверено 1 ноября 2026 г.). Включены поля Pydantic Settings из `libs/common/src/common/config.py`, параметры из `.env.shared.example`, переменные инфраструктуры Docker Compose/Traefik и переменная запуска worker-процесса.

## Как читать колонку «Обязательная»

- **Да** означает, что без значения соответствующий сервис или функция не сможет нормально стартовать/работать.
- **Условно** означает, что настройка нужна только при включении конкретной интеграции или механизма.
- **Нет** означает, что приложение использует значение по умолчанию или функциональность отключена/не используется.
- Обязательность относится к сервисам, указанным в описании, а не ко всем контейнерам сразу.

`—` в колонке значения по умолчанию означает, что код не задаёт дефолт. Для полей со сложным типом указано значение, создаваемое `default_factory`.

## Таблица

| Переменная окружения | Для чего нужна | Значение по умолчанию | Обязательная? |
|---|---|---:|---|
| `APP__ENVIRONMENT` | Окружение приложения; определяет выбор env-файлов и имя окружения в логах. | `dev` | Нет |
| `APP__DEBUG` | Режим подробного логирования. | `false` | Нет |
| `APP__VERSION` | Версия приложения, отображается в логах Sales Agent. | `0.1.0` | Нет |
| `DATABASE__URL` | Строка подключения к PostgreSQL (или SQLite); backend и миграции используют её для БД. | `—` | Да, для backend и миграций |
| `REDIS__URL` | Подключение к Redis для кеша и event bus; event bus требует его при включении. | `—` | Нет, если eventing выключен; да, если включён |
| `SERVICE__API_KEY` | Общий секрет межсервисной авторизации. | `—` | Условно: нужен для защищённых service-to-service запросов |
| `SERVICE__HEADER` | Имя HTTP-заголовка для SERVICE__API_KEY. | `X-Service-Key` | Нет |
| `SALES_AGENT__URL` | URL Sales Agent, используемый Telegram/Wappi-модулями для передачи входящих сообщений. | `—` | Да для соответствующих transport-модулей |
| `BACKEND__URL` | URL Backend API, который используют Sales Agent и transport-модули. | `—` | Да для Sales Agent и transport-модулей |
| `CORS__ALLOW_ORIGINS` | Список разрешённых браузерных origin для CORS. | `[]` | Нет |
| `CORS__ALLOW_METHODS` | Разрешённые HTTP-методы CORS. | `["*"]` | Нет |
| `CORS__ALLOW_HEADERS` | Разрешённые HTTP-заголовки CORS. | `["*"]` | Нет |
| `CORS__EXPOSE_HEADERS` | Заголовки ответа, доступные браузерному JavaScript. | `[]` | Нет |
| `CORS__ALLOW_CREDENTIALS` | Разрешает передачу credentials в браузерных CORS-запросах. | `false` | Нет |
| `CORS__MAX_AGE` | Время кеширования preflight-ответа, секунд. | `600` | Нет |
| `AUTH__JWT_SECRET_KEY` | Секрет подписи JWT access/refresh токенов Backend. | `—` | Да, для Backend |
| `AUTH__JWT_ALGORITHM` | Алгоритм подписи JWT. | `HS256` | Нет |
| `AUTH__ACCESS_TOKEN_EXPIRE_MINUTES` | Срок жизни access-токена в минутах. | `15` | Нет |
| `AUTH__REFRESH_TOKEN_EXPIRE_DAYS` | Срок жизни refresh-токена в днях. | `30` | Нет |
| `SENTRY__DSN` | DSN проекта Sentry для отправки ошибок Backend; без DSN интеграция отключена. | `—` | Нет |
| `SENTRY__SEND_DEFAULT_PII` | Разрешает отправку PII (например, IP и заголовков) в Sentry. | `true` | Нет |
| `SENTRY__TRACES_SAMPLE_RATE` | Доля трассировок, отправляемых в Sentry (0..1). | `0.5` | Нет |
| `SENTRY__ENVIRONMENT` | Имя окружения для Sentry; если не задано, берётся APP__ENVIRONMENT. | `—` | Нет |
| `TRANSPORT__TELEGRAM__URL` | URL Telegram transport module для запросов Backend. | `—` | Нет, если Telegram-интеграция не используется |
| `TRANSPORT__TELEGRAM__RELOAD_URL` | Необязательный URL endpoint принудительной перезагрузки Telegram-модуля. | `—` | Нет |
| `TRANSPORT__WAPPI__URL` | URL Wappi transport module для запросов Backend. | `—` | Нет, если Wappi-интеграция не используется |
| `TRANSPORT__WAZZUP__URL` | URL Wazzup transport module для запросов Backend. | `—` | Нет, если Wazzup-интеграция не используется |
| `TRANSPORT__TELEGRAM__ENDPOINT` | URL Telegram transport для исходящих доставок из Sales Agent. | `—` | Нет, если используется другой путь доставки |
| `EVENTING__ENABLED` | Включает обмен событиями через Redis Streams. | `false` | Нет |
| `EVENTING__BROKER` | Тип брокера событий. | `redis_streams` | Нет |
| `EVENTING__STREAM__NAME` | Название Redis Stream. | `backend.events` | Нет |
| `EVENTING__STREAM__GROUP` | Consumer group; обязателен при EVENTING__ENABLED=true. | `"" (пустая строка)` | Да, если eventing включён |
| `EVENTING__STREAM__CONSUMER_NAME` | Имя экземпляра consumer; по умолчанию hostname контейнера. | `hostname контейнера` | Нет; формируется автоматически |
| `EVENTING__STREAM__BLOCK_MS` | Время блокирующего ожидания сообщений, миллисекунды. | `5000` | Нет |
| `EVENTING__STREAM__COUNT` | Максимум сообщений за одно чтение. | `10` | Нет |
| `S3__ENDPOINT_URL` | Адрес S3-совместимого хранилища (в Docker обычно http://minio:9000). | `—` | Да для Backend и сервисов, использующих S3 |
| `S3__ACCESS_KEY_ID` | Ключ доступа S3/MinIO. | `—` | Да для Backend и сервисов, использующих S3 |
| `S3__SECRET_ACCESS_KEY` | Секретный ключ S3/MinIO. | `—` | Да для Backend и сервисов, использующих S3 |
| `S3__BUCKET_NAME` | Имя bucket для медиафайлов. | `—` | Да для Backend и сервисов, использующих S3 |
| `S3__REGION_NAME` | Регион S3. | `—` | Нет |
| `S3__USE_SSL` | Использовать TLS для подключения к S3. | `false` | Нет |
| `ENCRYPTION__MASTER_KEY` | Главный ключ шифрования сохранённых credentials интеграций (Fernet-compatible base64). | `—` | Условно: требуется при использовании шифрования credentials |
| `ARTIFACT_UPLOAD__MAX_RETRIES` | Максимальное число повторов загрузки артефактов. | `3` | Нет |
| `ARTIFACT_UPLOAD__RETRY_DELAY_S` | Базовая задержка повторной загрузки, секунды. | `1.0` | Нет |
| `LLM__BASE_URL` | Base URL OpenAI-совместимого API для основного LLM. | `https://api.openai.com/v1` | Нет |
| `LLM__API_KEY` | API-ключ основного LLM; Sales Agent проверяет наличие при создании LLM-клиента. | `—` | Да для запуска Sales Agent |
| `LLM__LIGHT_MODEL` | Имя лёгкой модели. | `gpt-4o-mini` | Нет |
| `LLM__LARGE_MODEL` | Имя основной/большой модели. | `gpt-4o` | Нет |
| `LANGFUSE__ENABLED` | Включает Langfuse telemetry. | `false` | Нет |
| `LANGFUSE__PUBLIC_KEY` | Публичный ключ Langfuse. | `—` | Нет; нужен при LANGFUSE__ENABLED=true |
| `LANGFUSE__SECRET_KEY` | Секретный ключ Langfuse. | `—` | Нет; нужен при LANGFUSE__ENABLED=true |
| `LANGFUSE__HOST` | Адрес Langfuse API. | `—` | Нет |
| `LANGFUSE__SAMPLE_RATE` | Доля генераций/трассировок, передаваемых в telemetry. | `1.0` | Нет |
| `LANGFUSE__ENABLE_GENERATION_CALLBACK_ONLY` | Ограничивает callback-интеграцию генерациями. | `true` | Нет |
| `YANDEX__TOKEN` | API-токен Yandex для функций, которым нужен Yandex API. | `—` | Нет; только для соответствующих возможностей |
| `RAG__ENABLED` | Включает функциональность RAG. | `true` | Нет |
| `RAG__DEFAULT_KB` | База знаний по умолчанию. | `default` | Нет |
| `RAG__EMBEDDING__BASE_URL` | Endpoint OpenAI-совместимого API эмбеддингов. | `—` | Да для индексации/поиска с embeddings |
| `RAG__EMBEDDING__API_KEY` | Ключ API эмбеддингов. | `—` | Да для индексации/поиска с embeddings |
| `RAG__EMBEDDING__MODEL` | Имя модели эмбеддингов. | `BAAI/bge-m3` | Нет |
| `RAG__EMBEDDING__DIMENSION` | Размерность вектора эмбеддинга. | `1024` | Нет |
| `RAG__EMBEDDING__TIMEOUT_S` | Таймаут API эмбеддингов, секунды. | `30.0` | Нет |
| `RAG__QDRANT__URL` | URL Qdrant vector store. | `—` | Да для Qdrant-поиска/хранения |
| `RAG__QDRANT__API_KEY` | API-ключ Qdrant. | `—` | Да для Qdrant Cloud |
| `RAG__QDRANT__COLLECTION_PREFIX` | Префикс имён коллекций Qdrant. | `kb` | Нет |
| `RAG__QDRANT__PREFER_SPARSE` | Предпочитать sparse-векторы (в текущем store dense-only, параметр объявлен в настройках). | `false` | Нет |
| `RAG__RERANKER__ENABLED` | Включает reranker Cohere. | `false` | Нет |
| `RAG__RERANKER__API_KEY` | Ключ API Cohere reranker. | `—` | Да, если reranker включён |
| `RAG__RERANKER__MODEL` | Имя модели reranker; в коде при пустом значении используется rerank-english-v3.0. | `"" (пустая строка); фактически fallback rerank-english-v3.0` | Нет |
| `RAG__RERANKER__TIMEOUT_S` | Таймаут reranker; поле настроек. | `30.0` | Нет |
| `RAG__CHUNK_MAX_TOKENS` | Максимум токенов в chunk базы знаний. | `800` | Нет |
| `RAG__CHUNK_OVERLAP_TOKENS` | Перекрытие соседних chunks, токены. | `120` | Нет |
| `DEBOUNCE__WINDOW_SECONDS` | Общее окно объединения/подавления сообщений бездействия, секунды. | `45` | Нет |
| `DEBOUNCE__PER_CHANNEL` | Словарь переопределения debounce-окна по channel; вложенные ключи задаются через __. | `{}` | Нет |
| `HUMANIZER__ENABLED` | Включает humanizer ответов. | `true` | Нет |
| `FAQ__ENABLED` | Включает FAQ matching. | `true` | Нет |
| `FAQ__THRESHOLD` | Порог совпадения FAQ (0..1). | `0.82` | Нет |
| `FAQ__PATH` | Путь к файлу FAQ, если используется файловый источник. | `—` | Нет |
| `FAQ__USE_QDRANT` | Использовать Qdrant для FAQ. | `false` | Нет |
| `FAQ__KB_NAME` | Имя базы знаний FAQ. | `faq` | Нет |
| `AUDIO__MODEL` | Модель транскрибации аудио. | `gpt-4o-mini-transcribe` | Нет |
| `AUDIO__BASE_URL` | Переопределение endpoint транскрибации; при отсутствии используется endpoint SDK/OpenAI по умолчанию. | `—` | Нет |
| `AUDIO__API_KEY` | API-ключ сервиса транскрибации аудио. | `—` | Да, если используется транскрибация |
| `AUDIO__MAX_AUDIO_BYTES` | Максимальный размер входного аудио, байты. | `15000000` | Нет |
| `AUDIO__SUPPORTED_MIMES` | Список MIME-типов аудио. | `["audio/ogg", "audio/opus", "audio/mpeg"]` | Нет |
| `AUDIO__TIMEOUT_S` | Таймаут транскрибации, секунды. | `60.0` | Нет |
| `AUDIO__TRANSCODE_ENABLED` | Включает предварительное перекодирование аудио через ffmpeg. | `true` | Нет |
| `AUDIO__FFMPEG_PATH` | Путь к исполняемому ffmpeg внутри контейнера. | `ffmpeg` | Нет |
| `CONNECTORS__<ID>__...` | Динамическая конфигурация коннекторов Sales Agent: TYPE, CHANNEL_TYPES, SECRETS, CALLBACKS, DEBOUNCE, TRANSPORT, METADATA и ENABLED. ID - произвольный идентификатор коннектора; точные вложенные поля описаны схемой ConnectorSettings. | `Тип messaging; enabled=true; прочие поля пустые/по умолчанию` | Нет глобально; зависит от настроенных коннекторов |
| `SALES_AGENT__CONNECTORS_REFRESH_INTERVAL_S` | Интервал обновления конфигурации коннекторов из Backend, секунды. | `1800.0` | Нет |
| `TELEGRAM_MODULE_PUBLIC_URL` | Публичный URL Telegram-модуля (необязательный адрес модуля). | `—` | Нет |
| `TELEGRAM_MODULE_REQUEST_TIMEOUT_S` | HTTP timeout Telegram-модуля. | `100.0` | Нет |
| `TELEGRAM_MODULE_CONFIG_REFRESH_INTERVAL_S` | Интервал обновления конфигурации Telegram-ботов, секунды. | `120.0` | Нет |
| `TELEGRAM_MODULE_SIGNATURE_TOLERANCE_S` | Допуск времени подписи Telegram webhook, секунды. | `300` | Нет |
| `TELEGRAM_MODULE_MAX_DELIVERY_ATTEMPTS` | Максимум попыток доставки Telegram-сообщения. | `3` | Нет |
| `TELEGRAM_MODULE_ALERT_AFTER_FAILURES` | Число последовательных ошибок до alert event. | `2` | Нет |
| `TELEGRAM_MODULE_DROP_PENDING_ON_WEBHOOK_RESET` | Удалять ожидающие updates при сбросе webhook. | `true` | Нет |
| `TELEGRAM_MODULE_POLLING_TIMEOUT_S` | Long-polling timeout Telegram Bot API, секунды. | `25.0` | Нет |
| `WAPPI_MODULE_REQUEST_TIMEOUT_S` | HTTP timeout Wappi-модуля. | `10.0` | Нет |
| `WAPPI_MODULE_CONFIG_REFRESH_INTERVAL_S` | Интервал обновления коннекторов Wappi, секунды. | `60.0` | Нет |
| `WAPPI_MODULE_MAX_DELIVERY_ATTEMPTS` | Максимум попыток доставки через Wappi. | `3` | Нет |
| `WAPPI_MODULE_INITIAL_SYNC_MESSAGES_LIMIT` | Максимум сообщений на диалог при первоначальной синхронизации. | `50` | Нет |
| `WAPPI_MODULE_INITIAL_SYNC_DIALOGS_LIMIT` | Максимум диалогов при первоначальной синхронизации. | `50` | Нет |
| `WAZZUP_MODULE_REQUEST_TIMEOUT_S` | HTTP timeout Wazzup-модуля. | `10.0` | Нет |
| `WAZZUP_MODULE_CONFIG_REFRESH_INTERVAL_S` | Интервал обновления коннекторов Wazzup, секунды. | `60.0` | Нет |
| `WAZZUP_MODULE_MAX_DELIVERY_ATTEMPTS` | Максимум попыток доставки через Wazzup. | `3` | Нет |
| `WAZZUP_MODULE_WEBHOOK_URL` | Публичный URL, на который Wazzup отправляет webhooks. | `—` | Да, если подключён Wazzup webhook |
| `MINIO_ROOT_USER` | Root-пользователь MinIO, используется контейнером MinIO. | `в compose-шаблоне явно не задан; в .env.shared.example minioadmin` | Да для MinIO |
| `MINIO_ROOT_PASSWORD` | Root-пароль MinIO. | `в compose-шаблоне явно не задан; в .env.shared.example minioadmin` | Да для MinIO |
| `DOMAIN_BACKEND` | Домен Backend для HTTPS-маршрута Traefik. | `пусто (маршрут пропускается)` | Нет |
| `DOMAIN_SALES` | Домен Sales Agent для HTTPS-маршрута Traefik. | `пусто (маршрут пропускается)` | Нет |
| `DOMAIN_CONNECTOR_HUB` | Домен connector hub; текущий generate-config.sh направляет его на wappi-module. | `пусто (маршрут пропускается)` | Нет |
| `ACME_EMAIL` | Email для Let's Encrypt ACME. | `admin@ai-gency.ru (fallback в docker-compose.yml)` | Нет, но рекомендуется для TLS |
| `WORKERS` | Перечень/имя backend worker-ов для запуска worker hub; задаётся Compose или командой запуска, не Settings. | `зависит от команды; в Compose: all` | Нужно для отдельного процесса worker-hub |

## Важные замечания по текущему репозиторию

1. `DATABASE__URL` в модели допускает `None`, но `Backend` обращается к `resolved_database_url`, который завершится ошибкой, если URL не задан. Для запуска backend и `backend-migrations` переменная обязательна.
2. `AUTH__JWT_SECRET_KEY` объявлен без default и нужен Backend для подписи токенов.
3. Все четыре поля `S3__...` объявлены обязательными в `S3Settings`. Если S3 функциональность нужна (в текущем backend она используется для медиа), заполни их.
4. `LLM__API_KEY` не помечен required в Pydantic-модели, но `LLMClient.from_settings()` явно выбрасывает ошибку без ключа при старте Sales Agent.
5. `RAG__EMBEDDING__BASE_URL` и `RAG__EMBEDDING__API_KEY` обязательны только при создании клиента embeddings. `RAG__QDRANT__URL` и `RAG__QDRANT__API_KEY` требуются при создании QdrantStore. Не путай настройки RAG с обязательными для старта всех сервисов.
6. `AUDIO__API_KEY` требуется только для транскрибации. `AUDIO__FFMPEG_PATH` должен существовать внутри контейнера, если `AUDIO__TRANSCODE_ENABLED=true`; Dockerfile ставит ffmpeg в сервисные образы с `INSTALL_FFMPEG=true`.
7. `APP__ENVIRONMENT`, `APP_ENV` и `ENV` - специальные переключатели выбора env-файлов. Это не три независимых настройки окружения: код проверяет их именно в таком порядке и берёт первую непустую. В Docker, если ты передаёшь все настройки через `env_file: .env`, переменные из process environment имеют приоритет над dotenv-файлами Python.
8. `MINIO_ROOT_USER` и `MINIO_ROOT_PASSWORD` нужны самому контейнеру MinIO. Они не являются полями Pydantic `S3Settings`; клиент приложения использует `S3__ACCESS_KEY_ID` и `S3__SECRET_ACCESS_KEY`.
9. В текущем `docker-compose.yml` у Redis не задан `REDIS__URL` автоматически. Для связи сервисов в Docker задай `REDIS__URL=redis://redis:6379/0`, если Redis используется.
10. В текущем `docker-compose.yml` нет сервиса PostgreSQL. `DATABASE__URL` должен указывать на реально доступный PostgreSQL, например на сервис `postgres`, который понадобится добавить в Compose. `localhost` внутри контейнера указывает на сам контейнер, а не на VPS.
11. `DOMAIN_*` и `ACME_EMAIL` читаются shell-скриптом/Compose, а не Pydantic Settings. В текущем Traefik-скрипте настроены маршруты только `backend`, `sales` и `connector` (последний на `wappi-module`). Отдельного маршрута Wazzup скрипт сейчас не генерирует.
12. `WORKERS` используется конфигурацией запуска Compose/justfile, это не поле Settings. В compose для `worker-hub` установлено `WORKERS=all`.
13. Параметры `CONFIG_REFRESH_INTERVAL_S`, `REQUEST_TIMEOUT_S`, `PORT`, `MAX_DELIVERY_ATTEMPTS`, `IDEMPOTENCY_CACHE_TTL_S`, `BACKEND_CONNECTORS_PATH` из `apps/wappi-module/docs/CONFIGURATION.md` - устаревшая документация. Их нет в актуальном `WappiModuleSettings`; используй актуальные имена с префиксом `WAPPI_MODULE_` из таблицы.
14. Для динамических коннекторов `CONNECTORS__<ID>__...` допустимы ключи внутри схемы `ConnectorSettings`. Например: `CONNECTORS__ACME__TYPE`, `CONNECTORS__ACME__CHANNEL_TYPES__0`, `CONNECTORS__ACME__SECRETS__TOKEN`, `CONNECTORS__ACME__CALLBACKS__DELIVERY_URL`, `CONNECTORS__ACME__TRANSPORT__ENABLED`. На практике основная конфигурация коннекторов может приходить из Backend, а не из `.env`.
15. В `.env.shared.example` присутствуют demo credentials `minioadmin` и заглушки API-ключей. Не используй эти значения в production.

## Что минимально нужно заполнить для запуска текущего набора сервисов

- Backend + migrations: `DATABASE__URL`, `AUTH__JWT_SECRET_KEY`, `S3__ENDPOINT_URL`, `S3__ACCESS_KEY_ID`, `S3__SECRET_ACCESS_KEY`, `S3__BUCKET_NAME`.
- Sales Agent: `LLM__API_KEY`, `BACKEND__URL`; embeddings/Qdrant ключи и URL - если используешь RAG ingestion/search.
- Telegram/Wappi/Wazzup modules: `BACKEND__URL`, `SALES_AGENT__URL` (для Telegram/Wappi); `SERVICE__API_KEY`, если backend endpoints защищены межсервисным ключом.
- Redis: `REDIS__URL=redis://redis:6379/0`, если используешь кеш или eventing.
- MinIO: `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD` плюс совпадающие `S3__ACCESS_KEY_ID` и `S3__SECRET_ACCESS_KEY` у приложения.

## Источники в репозитории

- `libs/common/src/common/config.py` - определения всех Pydantic settings, defaults, aliases.
- `.env.shared.example`, `apps/backend/.env.example`, `apps/sales-agent/.env.example` - env-шаблоны.
- `docker-compose.yml`, `docker/traefik/generate-config.sh`, `docker/python-service.Dockerfile`, `justfile` - инфраструктурные переменные и запуск.
- `apps/backend/src/backend/modules/core/database.py`, `apps/backend/src/backend/main.py`, `apps/sales-agent/src/sales_agent/lifespan/clients.py`, `apps/sales-agent/src/sales_agent/rag/` и модули transport - фактическое использование и проверки на обязательность.

Репозиторий: https://github.com/mkcomru/sales-back
