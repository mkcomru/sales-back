# syntax=docker/dockerfile:1.4
ARG PACKAGE_NAME
ARG APP_PATH
ARG PYTHONPATH_SUFFIX=
ARG UVICORN_MODULE_PATH

FROM python:3.12-slim as base
ARG INSTALL_FFMPEG=false

RUN apt-get update && apt-get install --no-install-recommends -y \
    curl \
    $([ "$INSTALL_FFMPEG" = "true" ] && echo "ffmpeg") \
    && rm -rf /var/lib/apt/lists/*

RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

RUN mv /root/.local/bin/uv /usr/local/bin/uv && \
    chmod +x /usr/local/bin/uv

WORKDIR /app

FROM base as builder
ARG PACKAGE_NAME
ARG APP_PATH

# Copy only dependency files to maximize cache hits
COPY pyproject.toml uv.lock ./
COPY libs/common/pyproject.toml ./libs/common/pyproject.toml
COPY ${APP_PATH}/pyproject.toml ./${APP_PATH}/pyproject.toml

RUN uv sync --frozen --no-dev --package ${PACKAGE_NAME}

FROM base as runtime
ARG APP_PATH
ARG PYTHONPATH_SUFFIX
ARG UVICORN_MODULE_PATH
ENV UVICORN_MODULE_PATH=${UVICORN_MODULE_PATH}

COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

COPY pyproject.toml ./
COPY ${APP_PATH}/pyproject.toml ./${APP_PATH}/
COPY ${APP_PATH}/src ./${APP_PATH}/src
COPY libs/common/src ./libs/common/src
COPY docker/uvicorn-entrypoint.sh /app/uvicorn-entrypoint.sh
RUN sed -i 's/\r$//' /app/uvicorn-entrypoint.sh && \
    chmod +x /app/uvicorn-entrypoint.sh

RUN --mount=type=bind,source=.,target=/context \
    if [ -d "/context/${APP_PATH}/migrations" ]; then \
    cp -r /context/${APP_PATH}/migrations ./${APP_PATH}/migrations; \
    fi || true

ENV PYTHONPATH="/app/${APP_PATH}${PYTHONPATH_SUFFIX}:/app/libs/common/src:/app"

WORKDIR /app/${APP_PATH}

RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["/bin/sh", "/app/uvicorn-entrypoint.sh"]
