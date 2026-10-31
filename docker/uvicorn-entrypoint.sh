#!/bin/sh

if [ -z "${UVICORN_MODULE_PATH:-}" ]; then
    echo "UVICORN_MODULE_PATH is not set" >&2
    exit 1
fi

exec uvicorn "${UVICORN_MODULE_PATH}" --host 0.0.0.0 --port 8000
