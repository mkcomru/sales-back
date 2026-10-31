"""Centralized configuration for manual testing scripts."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    """Test configuration loaded from environment with sensible defaults."""

    base_url: str = os.getenv("BACKEND_URL", "http://localhost:8081")
    api_prefix: str = "/api/v1"

    superuser_email: str = os.getenv("TEST_EMAIL", "komarovdemian@yandex.ru")
    superuser_password: str = os.getenv("TEST_PASSWORD", "1234567890")

    service_api_key: str = os.getenv("SERVICE_API_KEY", "test-api-key")

    request_timeout: float = float(os.getenv("REQUEST_TIMEOUT", "30.0"))
    health_check_timeout: float = 5.0

    @property
    def api_url(self) -> str:
        return f"{self.base_url}{self.api_prefix}"


# Global config instance
config = Config()
