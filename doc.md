Итог анализа
Проверил код, конфиги, Docker-сборку, миграции и документацию. Ничего не менял. Ключевой вывод: проект можно поднять на одном сервере через Docker Compose, но текущий docker-compose.yml не запустится без отсутствующих env-файлов, а sales-agent в Docker останется без ffmpeg.

1. Обязательная инфраструктура
Компонент	Зачем	Обязательность
PostgreSQL 15/16	Основная БД backend, schema backend	Обязательно
Redis 7	Eventing, refresh коннекторов, WebSocket tickets	Обязательно при EVENTING__ENABLED=true, иначе опционально
S3-compatible storage	Медиа, артефакты, транскрипции	Обязательно для всех сервисов
S3 bucket	Должен существовать заранее	Обязательно
LLM API	Генерация ответов sales-agent	Обязательно
Embeddings + Qdrant	RAG/база знаний	Обязательно, если RAG__ENABLED=true
Reranker API	Переранжирование RAG	Опционально
Audio transcription API + ffmpeg	Голосовые сообщения	Обязательно для аудио
Langfuse, Sentry	Трейсинг/ошибки	Опционально
Yandex Geocoder	Гео-валидация	Опционально
YClients / Wappi / Wazzup / Telegram API	Внешние интеграции	По мере подключения
Traefik + DNS + Let's Encrypt	HTTPS и маршруты	Обязательно для публичного доступа

2. Сервисы и порты
Сервис	Внутренний порт	Внешний порт в compose	Роль
backend	8000	8081	CRM core, API, биллинг
backend-migrations	—	—	aerich upgrade, завершается
worker-hub	—	—	Фоновые задачи, пинги
sales-agent	8000	8080	Stateless LLM-executor
telegram-module	8000	8082	Telegram polling
wappi-module	8000	8083	Wappi
wazzup-module	8000	8084	Wazzup
redis	6379	6379	Redis
minio	9000/9001	9000/9001	Только profile minio
traefik	80/443	80/443	Только profile server
Порядок запуска: PostgreSQL → Redis → S3 → миграции → backend → worker-hub → sales-agent → транспорты.

3. Минимальный набор env
Все сервисы:
APP__ENVIRONMENT=prod

S3__ENDPOINT_URL=https://...
S3__ACCESS_KEY_ID=...
S3__SECRET_ACCESS_KEY=...
S3__BUCKET_NAME=...
S3__REGION_NAME=...
S3__USE_SSL=true

SERVICE__API_KEY=<один и тот же ключ во всех сервисах>

REDIS__URL=redis://:<password>@redis:6379/0
EVENTING__ENABLED=true
Backend:
DATABASE__URL=postgresql://user:pass@postgres:5432/sales_bot?sslmode=require
AUTH__JWT_SECRET_KEY=<secret>

ENCRYPTION__MASTER_KEY=<Fernet key>
SALES_AGENT__URL=http://sales-agent:8000

TRANSPORT__TELEGRAM__URL=http://telegram-module:8000
TRANSPORT__WAPPI__URL=http://wappi-module:8000
TRANSPORT__WAZZUP__URL=http://wazzup-module:8000

CORS__ALLOW_ORIGINS=["https://admin.example.com"]
Sales-agent:
BACKEND__URL=http://backend:8000/api/v1

LLM__BASE_URL=...
LLM__API_KEY=...
LLM__LIGHT_MODEL=...
LLM__LARGE_MODEL=...

RAG__ENABLED=true
RAG__EMBEDDING__BASE_URL=...
RAG__EMBEDDING__API_KEY=...
RAG__EMBEDDING__MODEL=...
RAG__EMBEDDING__DIMENSION=1024
RAG__QDRANT__URL=...
RAG__QDRANT__API_KEY=...

AUDIO__API_KEY=...
AUDIO__MODEL=gpt-4o-mini-transcribe
AUDIO__FFMPEG_PATH=ffmpeg

TRANSPORT__TELEGRAM__ENDPOINT=http://telegram-module:8000
Транспорты:
BACKEND__URL=http://backend:8000/api/v1
SALES_AGENT__URL=http://sales-agent:8000
Traefik:
DOMAIN_BACKEND=backend.example.com
DOMAIN_SALES=sales.example.com
DOMAIN_CONNECTOR_HUB=connector.example.com
ACME_EMAIL=admin@example.com
Важно:
- BACKEND__URL у транспортов и sales-agent должен включать /api/v1.
- SALES_AGENT__URL у backend не должен включать /api/v1.
- S3__* обязательны даже для sales-agent и транспортов: S3Settings падает с ValidationError, если их нет.
- AUTH__JWT_SECRET_KEY обязателен для backend.
- ENCRYPTION__MASTER_KEY нужен для сохранения/чтения credentials коннекторов. Потеря ключа = потеря доступа к сохранённым секретам.
- DATABASE__URL должен содержать host, port, user, password и database. Парсер требует явный порт.
- Пользователь БД должен иметь право CREATE SCHEMA для первой миграции.
- CORS__ORIGINS из документации неверен; реальное поле — CORS__ALLOW_ORIGINS.

4. Команды деплоя
# 1. Подготовить env
cp .env.shared.example .env.shared.dev
# заполнить .env.shared.dev и apps/*/.env

# 2. Собрать
docker compose build

# 3. Поднять Redis
docker compose up -d redis

# 4. Применить миграции
docker compose run --rm backend-migrations

# 5. Создать администратора и начальные данные
cd apps/backend
uv run python -m scripts.create_superuser \
  --first-name Admin --last-name User \
  --email admin@example.com --password '<password>' --superuser
uv run python -m scripts.seed_db \
  --company-name 'Company' --user-email admin@example.com
cd ../..

# 6. Запустить приложение
docker compose up -d backend worker-hub sales-agent \
  telegram-module wappi-module wazzup-module

# 7. Проверить
curl -f http://localhost:8081/health
curl -f http://localhost:8080/healthz
curl -f http://localhost:8082/healthz
curl -f http://localhost:8083/healthz
curl -f http://localhost:8084/healthz
Для HTTPS:
docker compose --profile server up -d traefik

5. Найденные блокеры и риски
 1. Нет .env.shared.dev. Compose жёстко ссылается на него, а make bootstrap создаёт .env.shared. Это разные файлы.
 2. Нет apps/<service>/.env. Compose требует их для всех сервисов.
 3. PostgreSQL нет в compose. Нужен внешний Postgres или отдельный сервис.
 4. S3 обязателен для всех, хотя документация называет MinIO опциональным.
 5. sales-agent собирается без ffmpeg. В compose у него нет INSTALL_FFMPEG: "true", хотя транскрипция вызывает ffmpeg.
 6. Traefik не маршрутизирует Wazzup. Генерируются только backend, sales, connector → wappi-module. Для Wazzup нужен отдельный route или внешний reverse proxy.
 7. DOMAIN_CONNECTOR_HUB ведёт только на Wappi. Это не общий hub.
 8. Redis и все сервисы опубликованы наружу. В production нужен внутренний network и закрытые порты.
 9. EVENTING__ENABLED по умолчанию false. Root .env не передаётся в контейнеры, поэтому без явной настройки eventing выключен.
10. Масштабирование sales-agent и транспортов опасно. Debounce/idempotency частично in-memory; при нескольких репликах поведение ломается.
11. Скрипты create_superuser, seed_db, encrypt_connector_credentials не копируются в Docker-образ. Их нужно запускать с хоста из репозитория или монтировать в контейнер.
12. seed_db читает agent.md из apps/sales-agent/.... В backend-контейнере этого файла нет.
13. Документация устарела: порт Wappi 8002 вместо 8083, BACKEND__URL без /api/v1, CORS__ORIGINS вместо CORS__ALLOW_ORIGINS, неверные инструкции по Traefik.
14. Нет healthcheck у sales-agent и транспортов в compose. Зависимости стартуют, но без проверки их собственной готовности.
15. Нет автоматического создания S3 bucket.
16. Нужны бэкапы: PostgreSQL, S3 и ENCRYPTION__MASTER_KEY.
6. Что предлагаю сделать
1. Добавить в репозиторий рабочий шаблон .env.shared.dev.example и per-service .env.example.
2. Исправить compose: INSTALL_FFMPEG=true для sales-agent, healthcheck для всех сервисов, внутренняя сеть, закрыть Redis/порты.
3. Добавить Traefik route для Wazzup и опционально для Telegram webhook.
4. Добавить опциональный postgres service для dev/self-hosted или явно задокументировать managed Postgres.
5. Добавить скрипт проверки обязательных env до docker compose up.
6. Исправить документацию по URL, портам, CORS и env-файлам.
7. Прогнать smoke-тест: миграции → backend health → sales-agent health → тестовый inbound → ответ LLM → доставка в транспорт.

Вопросы
1. Целевая схема: один VPS + Docker Compose, или managed PostgreSQL/Redis/S3?
2. Чинить найденные проблемы в compose и документации сейчас, или сначала нужен только отчёт?