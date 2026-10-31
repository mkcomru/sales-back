from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from pydantic import SecretStr

from common.models.transport import TransportDeliveryPayload
from wazzup_module.connectors.models import WazzupConnectorConfig
from wazzup_module.services.wazzup_api import WazzupApiError
from wazzup_module.transport.service import TransportDeliveryService, _IdempotencyStore


def _make_connector(connector_id: str = "test-connector") -> WazzupConnectorConfig:
    return WazzupConnectorConfig(
        connector_id=connector_id,
        company_id="123",
        wazzup_api_key=SecretStr("api-key"),
        channel_id="chan-1",
        channel_type="instagram",
        metadata={"chat_id": "user-1"},
    )


def _make_payload(**overrides: Any) -> TransportDeliveryPayload:
    defaults: dict[str, Any] = {
        "connector_id": "test-connector",
        "company_id": "123",
        "channel_type": "instagram",
        "user_id": "user-1",
        "conversation_id": "conv-1",
        "correlation_id": "corr-1",
        "replies": ["Hello"],
        "metadata": {"chat_id": "user-1"},
    }
    defaults.update(overrides)
    return TransportDeliveryPayload(**defaults)


def _headers(connector_id: str = "test-connector") -> dict[str, str]:
    return {
        "X-Service-Key": "test-api-key",  # noqa: S106
        "X-Connector-Id": connector_id,
    }


class TestIdempotencyStore:
    @pytest.mark.anyio
    async def test_reserve_first_time(self) -> None:
        store = _IdempotencyStore(ttl_seconds=60.0)
        assert await store.reserve("key-1") is True

    @pytest.mark.anyio
    async def test_reserve_duplicate(self) -> None:
        store = _IdempotencyStore(ttl_seconds=60.0)
        await store.reserve("key-1")
        assert await store.reserve("key-1") is False

    @pytest.mark.anyio
    async def test_reserve_different_keys(self) -> None:
        store = _IdempotencyStore(ttl_seconds=60.0)
        assert await store.reserve("key-1") is True
        assert await store.reserve("key-2") is True


class TestTransportDeliveryHandle:
    @pytest.mark.anyio
    async def test_handle_success(self, mock_transport_service: TransportDeliveryService) -> None:
        connector = _make_connector()
        mock_transport_service._connectors._connectors["test-connector"] = connector

        payload = _make_payload()
        with patch(
            "wazzup_module.services.wazzup_api.WazzupApiClient.send_message",
            new_callable=AsyncMock,
        ):
            response = await mock_transport_service.handle(payload=payload, headers=_headers())

        assert response.status_code == 202

    @pytest.mark.anyio
    async def test_handle_connector_not_found(self, mock_transport_service: TransportDeliveryService) -> None:
        payload = _make_payload()
        with pytest.raises(HTTPException) as exc_info:
            await mock_transport_service.handle(payload=payload, headers=_headers())
        assert exc_info.value.status_code == 404

    @pytest.mark.anyio
    async def test_handle_missing_connector_header(self, mock_transport_service: TransportDeliveryService) -> None:
        connector = _make_connector()
        mock_transport_service._connectors._connectors["test-connector"] = connector

        payload = _make_payload()
        headers = {"X-Service-Key": "test-api-key"}  # noqa: S106
        with pytest.raises(HTTPException) as exc_info:
            await mock_transport_service.handle(payload=payload, headers=headers)
        assert exc_info.value.status_code == 401

    @pytest.mark.anyio
    async def test_handle_connector_header_mismatch(self, mock_transport_service: TransportDeliveryService) -> None:
        connector = _make_connector()
        mock_transport_service._connectors._connectors["test-connector"] = connector

        payload = _make_payload()
        headers = _headers(connector_id="wrong-id")
        with pytest.raises(HTTPException) as exc_info:
            await mock_transport_service.handle(payload=payload, headers=headers)
        assert exc_info.value.status_code == 401

    @pytest.mark.anyio
    async def test_handle_invalid_service_key(self, mock_transport_service: TransportDeliveryService) -> None:
        connector = _make_connector()
        mock_transport_service._connectors._connectors["test-connector"] = connector

        payload = _make_payload()
        headers = {"X-Service-Key": "wrong-key", "X-Connector-Id": "test-connector"}  # noqa: S106
        with pytest.raises(HTTPException) as exc_info:
            await mock_transport_service.handle(payload=payload, headers=headers)
        assert exc_info.value.status_code == 401

    @pytest.mark.anyio
    async def test_handle_duplicate_correlation_id(self, mock_transport_service: TransportDeliveryService) -> None:
        connector = _make_connector()
        mock_transport_service._connectors._connectors["test-connector"] = connector

        payload = _make_payload()
        with patch(
            "wazzup_module.services.wazzup_api.WazzupApiClient.send_message",
            new_callable=AsyncMock,
        ):
            await mock_transport_service.handle(payload=payload, headers=_headers())
            response = await mock_transport_service.handle(payload=payload, headers=_headers())

        assert response.status_code == 409

    @pytest.mark.anyio
    async def test_handle_delivery_failure(self, mock_transport_service: TransportDeliveryService) -> None:
        connector = _make_connector()
        mock_transport_service._connectors._connectors["test-connector"] = connector

        payload = _make_payload()
        with (
            patch(
                "wazzup_module.services.wazzup_api.WazzupApiClient.send_message",
                new_callable=AsyncMock,
                side_effect=WazzupApiError("400 Bad Request"),
            ),
            pytest.raises(HTTPException) as exc_info,
        ):
            await mock_transport_service.handle(payload=payload, headers=_headers())

        assert exc_info.value.status_code == 502

    @pytest.mark.anyio
    async def test_handle_retries_on_rate_limit(self, mock_transport_service: TransportDeliveryService) -> None:
        connector = _make_connector()
        mock_transport_service._connectors._connectors["test-connector"] = connector

        payload = _make_payload()
        call_count = 0

        async def mock_send(**kwargs: Any) -> dict:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise WazzupApiError("429 Too Many Requests")
            return {}

        with (
            patch("wazzup_module.services.wazzup_api.WazzupApiClient.send_message", side_effect=mock_send),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            response = await mock_transport_service.handle(payload=payload, headers=_headers())

        assert response.status_code == 202
        assert call_count == 2

    @pytest.mark.anyio
    async def test_handle_empty_replies_skipped(self, mock_transport_service: TransportDeliveryService) -> None:
        connector = _make_connector()
        mock_transport_service._connectors._connectors["test-connector"] = connector

        payload = _make_payload(replies=["", "  ", "Hello"])
        with patch(
            "wazzup_module.services.wazzup_api.WazzupApiClient.send_message",
            new_callable=AsyncMock,
        ) as mock_send:
            response = await mock_transport_service.handle(payload=payload, headers=_headers())

        assert response.status_code == 202
        assert mock_send.call_count == 1
