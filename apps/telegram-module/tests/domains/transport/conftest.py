from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture(autouse=True)
def mock_asyncio_sleep():
    """Automatically mock asyncio.sleep for transport service tests to prevent retry delays."""
    with patch("asyncio.sleep", new_callable=AsyncMock):
        yield
