from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def mock_asyncio_sleep(request):
    """Automatically mock asyncio.sleep for transport service tests to prevent retry delays.

    Note: This does NOT apply to TestIdempotencyStore tests which need real sleeps for TTL expiration.
    """
    test_class_name = ""
    if hasattr(request.node, "cls") and request.node.cls is not None:
        test_class_name = request.node.cls.__name__

    if "TestIdempotencyStore" in test_class_name:
        yield
    else:
        with patch("asyncio.sleep", new_callable=AsyncMock):
            yield


@pytest.fixture(autouse=True)
def mock_httpx_client():
    """Automatically mock httpx.AsyncClient to prevent real HTTP calls and timeouts."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"status": "ok"}
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("httpx.AsyncClient", return_value=mock_client):
        yield
