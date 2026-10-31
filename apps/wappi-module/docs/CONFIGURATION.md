# Wappi Module — Configuration & Deployment

## Environment Variables

### Обязательные переменные

```bash
# Backend API URL (для загрузки конфигурации коннекторов и форвардинга webhook-ов)
BACKEND__URL=http://localhost:8001

# Сервисный ключ для авторизации между сервисами
SERVICE__API_KEY=your-secret-service-key  # pragma: allowlist secret
```

### Опциональные переменные

```bash
# Окружение (dev, staging, prod)
APP__ENVIRONMENT=dev

# Debug режим (подробные логи)
APP__DEBUG=true

# Интервал обновления конфигурации (секунды)
CONFIG_REFRESH_INTERVAL_S=60

# Таймаут HTTP запросов (секунды)
REQUEST_TIMEOUT_S=10.0

# Порт сервера
PORT=8002

# Максимальное количество попыток доставки
MAX_DELIVERY_ATTEMPTS=3

# TTL кеша для идемпотентности (секунды)
IDEMPOTENCY_CACHE_TTL_S=86400  # 24 часа

# Путь к endpoint конфигурации в backend
BACKEND_CONNECTORS_PATH=/transport/wappi/connectors
```

---

## Configuration File Locations

### Development

```bash
# Локальная разработка
apps/wappi-module/.env

# Или shared конфиг (рекомендуется)
.env.shared
```

### Production

```bash
# Docker/Kubernetes: переменные окружения
# Kubernetes ConfigMap + Secret

# Systemd service: EnvironmentFile
/etc/wappi-module/env
```

---

## Settings Class

```python
# wappi_module/config/settings.py
from common import WappiModuleSettings

class Settings(WappiModuleSettings):
    """Wappi module specific settings derived from shared defaults."""
    pass

# Использование
settings = Settings()  # Автоматически загружает из env
```

### Shared Settings (libs/common)

```python
# libs/common/src/common/config.py
class WappiModuleSettings(BaseSettings):
    app: AppSettings
    service: ServiceSettings
    backend: BackendSettings
    config_refresh_interval_s: float = 60.0
    request_timeout_s: float = 10.0
    backend_connectors_path: str = "/transport/wappi/connectors"
    max_delivery_attempts: int = 3
    idempotency_cache_ttl_s: float = 86400.0
```

---

## Backend Integration

### Endpoint для загрузки коннекторов

```http
GET http://backend:8001/transport/wappi/connectors
X-Service-Key: {SERVICE__API_KEY}
```

### Response Format

```json
{
  "connectors": [
    {
      "connector_id": "test",
      "company_id": "1",
      "wappi_token": "your-wappi-api-token",
      "wappi_profile_id": "b51675ef-d41f-4891-9dd0-b74d76f5b9b5",
      "channel_type": "telegram",
      "metadata": {
        "api_base_url": "https://wappi.pro",
        "provider": "wappi-hub"
      }
    }
  ]
}
```

### Или как массив

```json
[
  {
    "connector_id": "test",
    "company_id": 1,
    "wappi_token": "your-wappi-api-token",
    "wappi_profile_id": "b51675ef-d41f-4891-9dd0-b74d76f5b9b5",
    "channel_type": "telegram",
    "metadata": {}
  }
]
```

### Database Schema (backend)

```sql
CREATE TABLE wappi_connectors (
    id SERIAL PRIMARY KEY,
    connector_id VARCHAR(255) UNIQUE NOT NULL,
    company_id INTEGER NOT NULL,
    wappi_token TEXT NOT NULL,
    wappi_profile_id VARCHAR(255) NOT NULL,  -- ПОЛНЫЙ UUID (36 символов)!
    channel_type VARCHAR(50) DEFAULT 'telegram',
    metadata JSONB DEFAULT '{}',
    enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Индексы
CREATE INDEX idx_wappi_connectors_company ON wappi_connectors(company_id);
CREATE INDEX idx_wappi_connectors_enabled ON wappi_connectors(enabled);
```

### Пример INSERT

```sql
INSERT INTO wappi_connectors (
    connector_id,
    company_id,
    wappi_token,
    wappi_profile_id,
    channel_type,
    metadata
) VALUES (
    'test',
    1,
    'your-wappi-api-token',
    'b51675ef-d41f-4891-9dd0-b74d76f5b9b5',  -- Полный UUID!
    'telegram',
    '{"api_base_url": "https://wappi.pro", "provider": "wappi-hub"}'::jsonb
);
```

---

## Wappi Dashboard Configuration

### 1. Получение API credentials

1. Зайдите в [Wappi Dashboard](https://wappi.pro/dashboard)
2. Создайте профиль (или выберите существующий)
3. Скопируйте:
   - **API Token** → `wappi_token`
   - **Profile ID** → `wappi_profile_id` (полный UUID!)

### 2. Настройка Webhook URL

**URL:** `https://your-domain.com/wappi/{connector_id}/webhook`

Пример: `https://api.example.com/wappi/test/webhook`

**Важно:**
- Используйте HTTPS (для production)
- `{connector_id}` должен совпадать с `connector_id` в БД
- URL должен быть публично доступен (или используйте ngrok для dev)

### 3. Тестирование webhook

Wappi Dashboard обычно предоставляет кнопку "Test Webhook" — используйте её для проверки.

---

## Docker Deployment

### Dockerfile

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Установка uv
RUN pip install uv

# Копирование зависимостей
COPY pyproject.toml uv.lock ./
COPY libs/common libs/common

# Установка зависимостей
RUN uv sync --no-dev

# Копирование исходников
COPY apps/wappi-module ./apps/wappi-module

# Открываем порт
EXPOSE 8002

# Запуск
CMD ["uv", "run", "--package", "wappi-module", "uvicorn", "wappi_module.main:app", "--host", "0.0.0.0", "--port", "8002"]
```

### Docker Compose

```yaml
version: '3.8'

services:
  wappi-module:
    build:
      context: .
      dockerfile: apps/wappi-module/Dockerfile
    ports:
      - "8002:8002"
    environment:
      - BACKEND__URL=http://backend:8001
      - SERVICE__API_KEY=${SERVICE__API_KEY}  # pragma: allowlist secret
      - APP__ENVIRONMENT=production
      - APP__DEBUG=false
    depends_on:
      - backend
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8002/healthz"]
      interval: 30s
      timeout: 5s
      retries: 3

  backend:
    image: backend:latest
    # ...
```

### Running

```bash
# Development
docker-compose up wappi-module

# Production
docker-compose -f docker-compose.prod.yml up -d wappi-module
```

---

## Kubernetes Deployment

### ConfigMap

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: wappi-module-config
  namespace: sales-bot
data:
  BACKEND__URL: "http://backend.sales-bot.svc.cluster.local:8001"
  APP__ENVIRONMENT: "production"
  APP__DEBUG: "false"
  CONFIG_REFRESH_INTERVAL_S: "60"
  REQUEST_TIMEOUT_S: "10"
  BACKEND_CONNECTORS_PATH: "/transport/wappi/connectors"
```

### Secret

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: wappi-module-secrets
  namespace: sales-bot
type: Opaque
stringData:
  SERVICE__API_KEY: "your-secret-service-key"  # pragma: allowlist secret
```

### Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: wappi-module
  namespace: sales-bot
spec:
  replicas: 2
  selector:
    matchLabels:
      app: wappi-module
  template:
    metadata:
      labels:
        app: wappi-module
    spec:
      containers:
      - name: wappi-module
        image: your-registry/wappi-module:latest
        ports:
        - containerPort: 8002
          name: http
        envFrom:
        - configMapRef:
            name: wappi-module-config
        - secretRef:
            name: wappi-module-secrets
        resources:
          requests:
            memory: "128Mi"
            cpu: "100m"
          limits:
            memory: "512Mi"
            cpu: "500m"
        livenessProbe:
          httpGet:
            path: /healthz
            port: 8002
          initialDelaySeconds: 10
          periodSeconds: 30
        readinessProbe:
          httpGet:
            path: /healthz
            port: 8002
          initialDelaySeconds: 5
          periodSeconds: 10
```

### Service

```yaml
apiVersion: v1
kind: Service
metadata:
  name: wappi-module
  namespace: sales-bot
spec:
  selector:
    app: wappi-module
  ports:
  - protocol: TCP
    port: 8002
    targetPort: 8002
  type: ClusterIP
```

### Ingress (для webhook-ов от Wappi)

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: wappi-module-ingress
  namespace: sales-bot
  annotations:
    cert-manager.io/cluster-issuer: "letsencrypt-prod"
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
spec:
  tls:
  - hosts:
    - api.example.com
    secretName: wappi-module-tls
  rules:
  - host: api.example.com
    http:
      paths:
      - path: /wappi
        pathType: Prefix
        backend:
          service:
            name: wappi-module
            port:
              number: 8002
```

---

## Systemd Service (Linux)

### Service File

```ini
# /etc/systemd/system/wappi-module.service
[Unit]
Description=Wappi Module for Sales Bot
After=network.target

[Service]
Type=simple
User=wappi-module
Group=wappi-module
WorkingDirectory=/opt/sales-bot/apps/wappi-module
EnvironmentFile=/etc/wappi-module/env
ExecStart=/usr/local/bin/uv run uvicorn wappi_module.main:app --host 0.0.0.0 --port 8002
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### Environment File

```bash
# /etc/wappi-module/env
BACKEND__URL=http://localhost:8001
SERVICE__API_KEY=your-secret-service-key  # pragma: allowlist secret
APP__ENVIRONMENT=production
APP__DEBUG=false
```

### Commands

```bash
# Установка
sudo systemctl daemon-reload
sudo systemctl enable wappi-module

# Управление
sudo systemctl start wappi-module
sudo systemctl stop wappi-module
sudo systemctl restart wappi-module

# Логи
sudo journalctl -u wappi-module -f
```

---

## Development Setup

### 1. Установка зависимостей

```bash
# Из корня репозитория
uv sync
```

### 2. Настройка .env

```bash
# Скопировать пример
cp .env.example .env.shared

# Отредактировать значения
nano .env.shared
```

### 3. Запуск backend (и sales-agent, если требуется)

```bash
# Terminal 1: backend
cd apps/backend
uv run uvicorn backend.main:app --reload --port 8001

# Terminal 2: sales-agent (если требуется для обработки сообщений)
cd apps/sales-agent
uv run uvicorn src.sales_agent.main:app --reload --port 8000
```

### 4. Запуск wappi-module

```bash
# Terminal 3: wappi-module
cd apps/wappi-module
uv run uvicorn wappi_module.main:app --reload --port 8002
```

### 5. Проверка

```bash
# Health check
curl http://localhost:8002/healthz

# Проверка загрузки коннекторов (логи)
# Должно быть: connector.reload.completed count=N
```

---

## Monitoring & Observability

### Structured Logging

**Формат:** JSON (structlog)

```json
{
  "event": "transport.delivery.delivered",
  "level": "info",
  "timestamp": "2024-11-21T12:01:58.194436Z",
  "correlation_id": "sa331c532f",
  "connector_id": "test",
  "company_id": "1",
  "attempt": 1,
  "delivery_index": 0
}
```

### Log Aggregation

**ELK Stack:**
```yaml
# filebeat.yml
filebeat.inputs:
- type: container
  paths:
    - '/var/lib/docker/containers/*/*.log'
  processors:
    - add_kubernetes_metadata:
        host: ${NODE_NAME}
        matchers:
        - logs_path:
            logs_path: "/var/lib/docker/containers/"

output.elasticsearch:
  hosts: ["elasticsearch:9200"]
```

**Grafana Loki:**
```yaml
# promtail-config.yaml
clients:
  - url: http://loki:3100/loki/api/v1/push

scrape_configs:
  - job_name: wappi-module
    kubernetes_sd_configs:
      - role: pod
    relabel_configs:
      - source_labels: [__meta_kubernetes_pod_label_app]
        target_label: app
```

### Metrics (future)

```python
# Prometheus counters (планируется)
wappi_module_messages_delivered_total
wappi_module_messages_failed_total
wappi_module_webhooks_received_total
wappi_module_connector_reload_count
```

---

## Security Best Practices

### 1. Service Key Rotation

```bash
# Генерация нового ключа
openssl rand -hex 32

# Обновление в БД и env файлах всех сервисов
# Рестарт сервисов
```

### 2. Secrets Management

**Kubernetes:**
```bash
# Использовать External Secrets Operator
kubectl apply -f external-secret.yaml
```

**Docker Swarm:**
```bash
# Использовать Docker Secrets
echo "secret-key" | docker secret create service_api_key -  # pragma: allowlist secret
```

**HashiCorp Vault:**
```bash
# Интеграция с Vault
vault kv put secret/wappi-module \
  service_api_key="..." \  # pragma: allowlist secret
  wappi_token="..."  # pragma: allowlist secret
```

### 3. Network Policies (Kubernetes)

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: wappi-module-policy
spec:
  podSelector:
    matchLabels:
      app: wappi-module
  policyTypes:
  - Ingress
  - Egress
  ingress:
  - from:
    - podSelector:
        matchLabels:
          app: sales-agent
    ports:
    - protocol: TCP
      port: 8002
  egress:
  - to:
    - podSelector:
        matchLabels:
          app: backend
    ports:
    - protocol: TCP
      port: 8001
  - to:
    - podSelector:
        matchLabels:
          app: sales-agent
    ports:
    - protocol: TCP
      port: 8000
```

---

## Performance Tuning

### Uvicorn Workers

```bash
# Многопоточный режим
uvicorn wappi_module.main:app \
  --host 0.0.0.0 \
  --port 8002 \
  --workers 4 \
  --loop uvloop \
  --log-level info
```

### HTTPX Connection Pool

```python
# wappi_api.py
async with httpx.AsyncClient(
    timeout=self._timeout,
    limits=httpx.Limits(
        max_keepalive_connections=10,
        max_connections=100
    )
) as client:
    # ...
```

### Idempotency Cache Cleanup

```python
# transport/service.py
async def _cleanup_old_deliveries(self) -> None:
    """Периодическая очистка устаревших записей из кеша"""
    now = time.time()
    expired = [
        cid for cid, ts in self._delivered_cache.items()
        if now - ts > self._settings.idempotency_cache_ttl_s
    ]
    for cid in expired:
        del self._delivered_cache[cid]
```

---

## Backup & Recovery

### Configuration Backup

```bash
# Backup из backend БД
pg_dump -U postgres -t wappi_connectors sales_bot > wappi_connectors_backup.sql

# Восстановление
psql -U postgres sales_bot < wappi_connectors_backup.sql
```

### State Recovery

**Идемпотентность кеш:**
- Хранится в памяти → при рестарте очищается
- Это безопасно: Sales Agent будет повторно отправлять, но в течение 24ч получит 409 Conflict
- Для persistent кеша используйте Redis

---

## Troubleshooting

См. [TROUBLESHOOTING.md](./TROUBLESHOOTING.md)

---

**Документ обновлён:** 2024-11-21  
**Версия модуля:** 0.1.0

