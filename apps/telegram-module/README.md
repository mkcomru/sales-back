# Telegram Transport Module

Сервис обслуживает доставку сообщений в Telegram Bot API и агрегирует ботов нескольких компаний. Он принимает `TransportDelivery` запросы от Backend (который маршрутизирует ответы от Sales Agent), проверяет единый сервисный ключ и гарантирует идемпотентность по `correlation_id`.

## Запуск

```bash
# Из корня репозитория:
uv run --package telegram-module uvicorn telegram_module.main:app --reload

# Или из папки модуля:
cd apps/telegram-module
uv run uvicorn telegram_module.main:app --reload
```

Необходимые переменные окружения (в `.env.shared`):
- `BACKEND__URL` — адрес backend для загрузки конфигурации ботов и отправки входящих сообщений.
- `SERVICE__API_KEY` — единый сервисный ключ для авторизации между сервисами.

## Архитектура

### Загрузка конфигурации
Модуль получает список Telegram-ботов из unified backend API:
```
GET /transport/connectors?type=telegram&enabled=true
```

Ответ содержит список коннекторов с конфигурацией:
```json
{
  "connectors": [
    {
      "connector_id": "tg-bot-abc123",
      "type": "telegram",
      "config": {
        "bot_token": "123456:ABC...",
        "mode": "polling"
      },
      "debounce_window_seconds": 45
    }
  ]
}
```

### Входящие сообщения
1. aiogram получает Telegram Update (polling или webhook)
2. Модуль нормализует Update в `InboundEnvelope`
3. Отправляет на Backend: `POST /api/v1/messages/inbound`
4. Авторизация: `X-Service-Key` + `X-Connector-Id` headers
5. Backend форвардит в Sales Agent: `POST /api/v1/internal/messages/inbound`

### Исходящие сообщения
1. Sales Agent формирует `OutboundDeliveryRequest` и отправляет в Backend: `POST /api/v1/internal/messages/outbound`
2. Backend маршрутизирует на модуль: `POST /transport/delivery`
3. Модуль проверяет `X-Service-Key`, `X-Connector-Id`
4. Доставляет в Telegram Bot API с ретраями

### Event-driven Updates
При изменении коннекторов в backend модуль получает `transport.connectors.changed` event через Redis Streams и автоматически обновляет конфигурацию ботов.

## Поток сообщений
1. Backend отдаёт список активных ботов через `GET /transport/connectors?type=telegram&enabled=true`
2. Входящие Telegram-апдейты нормализуются в `InboundEnvelope` и отправляются в Backend (`POST /api/v1/messages/inbound`)
3. Backend форвардит в Sales Agent (`POST /api/v1/internal/messages/inbound`)
4. Sales Agent обрабатывает сообщение и отправляет ответ в Backend (`POST /api/v1/internal/messages/outbound`)
5. Backend маршрутизирует `TransportDelivery` на модуль (`POST /transport/delivery`)
6. Модуль доставляет ответ в Telegram с ретраями при 429/5xx

## Диагностика
- `GET /healthz` — быстрый health‑чек
- `POST /admin/reload` — форс-обновление конфигурации ботов
- Логи `transport.delivery.*` содержат ключевые события доставки и ретраев
