from __future__ import annotations

import os
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from common import SalesAgentSettings

TEST_BACKEND_URL = "http://localhost:8001"
TEST_SERVICE_KEY = "test-service-key"  # pragma: allowlist secret

DEFAULT_ENV = {
    "APP__ENVIRONMENT": "test",
    "BACKEND__URL": TEST_BACKEND_URL,
    "SERVICE__API_KEY": TEST_SERVICE_KEY,
    "S3__ENDPOINT_URL": "http://localhost:9000",
    "S3__ACCESS_KEY_ID": "test-access-key",  # pragma: allowlist secret
    "S3__SECRET_ACCESS_KEY": "test-secret-key",  # pragma: allowlist secret
    "S3__BUCKET_NAME": "test-bucket",
}

for key, value in DEFAULT_ENV.items():
    os.environ.setdefault(key, value)


def _disable_env_files() -> None:
    import common.config as common_config

    common_config.SHARED_ENV_FILES = ()
    common_config.CommonSettingsBase.model_config["env_file"] = ()
    common_config.SalesAgentSettings._env_files = ()
    common_config.SalesAgentSettings.model_config["env_file"] = ()


_disable_env_files()


@pytest.fixture(scope="session")
def settings() -> SalesAgentSettings:
    return SalesAgentSettings()


@pytest.fixture
def mock_backend_client() -> AsyncMock:
    """Mock BackendClient for testing."""
    client = AsyncMock()
    client.get_customer_profile = AsyncMock(return_value={"customer_fields": {}, "rejected": False})
    client.get_customer_answers = AsyncMock(return_value={})
    client.update_customer_fields = AsyncMock()
    client.mark_customer_rejected = AsyncMock()
    client.get_or_create_thread = AsyncMock(return_value={"thread_id": "test-thread-1"})
    client.append_history_batch = AsyncMock()
    client.get_recent_history = AsyncMock(return_value=[])
    client.get_langfuse_session_id = AsyncMock(return_value=None)
    client.create_langfuse_session = AsyncMock(return_value="test-session-1")
    client.reset_customer_profile = AsyncMock()
    client.get_company_spec = AsyncMock(return_value={})
    return client


@pytest.fixture
def mock_httpx_client() -> MagicMock:
    """Mock httpx.AsyncClient for testing."""
    client = MagicMock()
    response = MagicMock()
    response.status_code = 200
    response.json = MagicMock(return_value={})
    response.raise_for_status = MagicMock()
    client.post = AsyncMock(return_value=response)
    client.get = AsyncMock(return_value=response)
    client.put = AsyncMock(return_value=response)
    client.delete = AsyncMock(return_value=response)
    return client


@pytest.fixture
def mock_llm_client() -> MagicMock:
    """Mock LLMClient for testing."""
    client = MagicMock()
    client.chat_completion = AsyncMock(return_value={"choices": [{"message": {"content": "test response"}}]})
    client.chat_completion_stream = AsyncMock()
    return client


@pytest.fixture
def sample_incoming_message() -> dict[str, Any]:
    """Sample IncomingMessage data."""
    return {
        "connector_id": "test-connector",
        "conversation_id": "test-conversation-1",
        "user_id": "123",
        "text": "Hello, world!",
        "attachments": [],
        "metadata": {"company_id": 1, "channel_type": "telegram"},
    }


@pytest.fixture
def sample_company_spec() -> dict[str, Any]:
    """Sample company spec data."""
    return {
        "name": "Test Company",
        "stages_config": [{"name": "new", "crm_id": "NEW", "display": "New", "summary": "New lead"}],
        "category_rules": [],
        "tools": [],
        "crm_default_stage_id": "PROCESSED",
        "crm_forward_metadata_keys": [],
    }
