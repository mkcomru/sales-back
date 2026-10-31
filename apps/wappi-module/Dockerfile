# syntax=docker/dockerfile:1.4
FROM python:3.12-slim as base

# Установка системных зависимостей
RUN apt-get update && apt-get install --no-install-recommends -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Установка uv package manager
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

RUN mv /root/.local/bin/uv /usr/local/bin/uv && \
    chmod +x /usr/local/bin/uv

WORKDIR /app

# ============================================================
# Builder stage - установка зависимостей
# ============================================================
FROM base as builder

# Копирование файлов зависимостей для uv
COPY pyproject.toml uv.lock ./
COPY libs/common/pyproject.toml libs/common/src ./libs/common/
COPY apps/wappi-module/pyproject.toml apps/wappi-module/src ./apps/wappi-module/

# Установка зависимостей без dev-пакетов
RUN uv sync --frozen --no-dev --package wappi-module

# ============================================================
# Runtime stage - финальный образ
# ============================================================
FROM base as runtime

# Копирование установленного виртуального окружения
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# Копирование исходного кода
COPY pyproject.toml ./
COPY apps/wappi-module/pyproject.toml ./apps/wappi-module/
COPY apps/wappi-module/src ./apps/wappi-module/src
COPY libs/common/src ./libs/common/src

# Настройка PYTHONPATH для корректного импорта модулей
ENV PYTHONPATH="/app/apps/wappi-module/src:/app/libs/common/src:/app"

# Создание непривилегированного пользователя для безопасности
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app
USER appuser

# Установка рабочей директории
WORKDIR /app/apps/wappi-module

# Порт для wappi-module (по умолчанию 8002)
EXPOSE 8002

# Запуск приложения через uvicorn
CMD ["uvicorn", "wappi_module.main:app", "--host", "0.0.0.0", "--port", "8002"]
