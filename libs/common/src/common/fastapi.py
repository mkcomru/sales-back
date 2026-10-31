from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import CorsSettings


def apply_cors(app: FastAPI, cors: CorsSettings | None) -> None:
    """Attach CORSMiddleware to the FastAPI app based on shared settings."""
    if cors is None or not cors.allow_origins:
        return

    state = getattr(app, "state", None)
    if state is not None and getattr(state, "_cors_configured", False):
        return

    allow_methods = cors.allow_methods or ["*"]
    allow_headers = cors.allow_headers or ["*"]
    expose_headers = cors.expose_headers or []
    allow_credentials = cors.allow_credentials

    if any(origin == "*" for origin in cors.allow_origins):
        allow_credentials = False

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors.allow_origins,
        allow_methods=allow_methods,
        allow_headers=allow_headers,
        expose_headers=expose_headers,
        allow_credentials=allow_credentials,
        max_age=cors.max_age,
    )

    if state is not None:
        state._cors_configured = True
