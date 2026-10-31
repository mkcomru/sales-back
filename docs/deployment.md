# Deployment Guide

Guide for deploying services using Docker Compose.

## Service Dependencies

Services must start in this order:

1. **Redis** - Required for eventing (if enabled)
2. **Backend migrations** - Database schema setup
3. **Backend** - CRM core (other services depend on it)
4. **Sales Agent** - Stateless LLM executor (no migrations)
5. **Transport modules** - telegram-module, wappi-module (depend on backend)

## Docker Compose Profiles

### Default Profile

Services run without profiles:

- `redis` - Redis instance
- `backend-migrations` - Backend database migrations
- `backend` - Backend service
- `sales-agent` - Sales Agent service
- `telegram-module` - Telegram transport

### Server Profile

Add `--profile server` to include:

- `traefik` - Reverse proxy with SSL termination

## Starting Services

### Development (All Services)

```bash
# Start all services
docker compose up

# Start with Traefik (production-like)
docker compose --profile server up
```

### Production-Like Setup

```bash
# Build all images
docker compose build

# Run migrations first
docker compose up backend-migrations

# Start services
docker compose up -d backend sales-agent telegram-module wappi-module
```

## Service Ports

- `backend`: `8081:8000` (external:internal)
- `sales-agent`: `8080:8000`
- `telegram-module`: `8082:8000`
- `wappi-module`: `8002:8000` (if added to compose)
- `redis`: `6379:6379`
- `traefik`: `80:80`, `443:443`, `8090:8080` (dashboard)

## Health Checks

All services expose health check endpoints:

- Backend: `GET /health`
- Sales Agent: `GET /healthz`
- Telegram Module: `GET /healthz`
- Wappi Module: `GET /healthz`

Docker Compose uses these for dependency management (`condition: service_healthy`).

## Migrations

Migrations run as separate services before main services start:

```bash
# Run migrations manually
docker compose up backend-migrations

```

Migrations use `aerich upgrade` command and exit after completion.

## Environment Files

Docker Compose loads environment files in order:

1. `.env.shared.dev` (or `.env.shared` if no env-specific file)
2. `apps/<module>/.env` (or `apps/<module>/.env.dev`)

Set `ENV=dev` or `APP__ENVIRONMENT=dev` to use environment-specific files.

## Volume Mounts

### Traefik

- `/var/run/docker.sock:/var/run/docker.sock:ro` - Docker socket access
- `traefik_letsencrypt:/letsencrypt` - SSL certificates storage

### Redis

- `redis_data:/data` - Redis persistence

## Traefik Configuration

When using `server` profile, Traefik provides:

- Automatic HTTPS with Let's Encrypt
- HTTP to HTTPS redirect
- Service discovery via Docker labels

Example labels (from `docker-compose.yml`):

```yaml
labels:
  - "traefik.enable=true"
  - "traefik.http.routers.backend-https.rule=Host(`sales-back.ai-gency.ru`)"
  - "traefik.http.routers.backend-https.tls=true"
  - "traefik.http.routers.backend-https.tls.certresolver=letsencrypt"
```

## Service Dependencies in Compose

Services declare dependencies:

- `backend` depends on: `redis` (healthy), `backend-migrations` (completed)
- `sales-agent` depends on: `redis` (healthy), `backend` (healthy)
- `telegram-module` depends on: `backend` (healthy)

## Environment Variables in Compose

Services can override environment variables:

```yaml
environment:
  EVENTING__STREAM__GROUP: backend
  EVENTING__STREAM__NAME: backend.events
```

These override values from `.env` files.

## Building Images

All services use shared Dockerfile with build args:

```bash
# Build specific service
docker compose build backend

# Build all services
docker compose build

# Build without cache
docker compose build --no-cache backend
```

Build args configured per service:
- `PACKAGE_NAME` - Package name for `uv sync`
- `APP_PATH` - Module path
- `PYTHONPATH_SUFFIX` - PYTHONPATH suffix
- `UVICORN_MODULE_PATH` - Uvicorn module path

## Logs

```bash
# View all logs
docker compose logs -f

# View specific service
docker compose logs -f backend

# View last 100 lines
docker compose logs --tail=100 backend
```

## Restart Policies

All services use `restart: unless-stopped` except migrations which use `restart: "no"`.

## Scaling

Services can be scaled horizontally:

```bash
# Scale telegram-module to 3 instances
docker compose up -d --scale telegram-module=3
```

Note: Each instance needs unique `EVENTING__STREAM__CONSUMER_NAME` (defaults to hostname, auto-scales).

## Production Considerations

1. **Secrets Management**: Use Docker secrets or external secret manager instead of `.env` files
2. **Database**: Use managed PostgreSQL service, not containerized
3. **Redis**: Use managed Redis service for production
4. **SSL**: Configure Traefik with proper domain and email for Let's Encrypt
5. **Monitoring**: Add health check monitoring and alerting
6. **Logging**: Configure log aggregation (ELK, Loki, etc.)
7. **Backups**: Set up database backups
8. **Resource Limits**: Add CPU/memory limits to services
