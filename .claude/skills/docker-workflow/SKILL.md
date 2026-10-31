---
name: docker-workflow
description: Apply when working with Docker, docker-compose, Dockerfile, or deployment configuration
allowed-tools: Read, Bash
---

- Для локальной разработки: `docker compose up -d`
- Для пересборки: `docker compose up -d --build`
- Всегда добавляй healthcheck для сервисов с базой данных
- Секреты только через `.env` файл, никогда не хардкодь в Dockerfile
- Multi-stage builds для production образов
