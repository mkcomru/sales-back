"""Tests for TransportDeliveryService."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from pydantic import SecretStr

from wappi_module.config import Settings
from wappi_module.connectors.manager import ConnectorManager
from wappi_module.connectors.models import WappiConnectorConfig
from wappi_module.services.backend import WappiBackendClient
from wappi_module.services.wappi_api import WappiApiError
from wappi_module.transport.models import TransportDeliveryPayload
from wappi_module.transport.service import (
    TransportDeliveryError,
    TransportDeliveryService,
    _IdempotencyStore,
)


class TestIdempotencyStore:
    @pytest.mark.asyncio
    async def test_reserve_new_key(self) -> None:
        store = _IdempotencyStore(ttl_seconds=10.0)

        result = await store.reserve("key1")

        assert result is True

    @pytest.mark.asyncio
    async def test_reserve_duplicate_key(self) -> None:
        store = _IdempotencyStore(ttl_seconds=10.0)

        first = await store.reserve("key1")
        second = await store.reserve("key1")

        assert first is True
        assert second is False

    @pytest.mark.asyncio
    async def test_reserve_expired_key(self) -> None:
        store = _IdempotencyStore(ttl_seconds=0.01)

        first = await store.reserve("key1")
        await asyncio.sleep(0.02)
        second = await store.reserve("key1")

        assert first is True
        assert second is True

    @pytest.mark.asyncio
    async def test_purge_expired_entries(self) -> None:
        store = _IdempotencyStore(ttl_seconds=0.01)

        await store.reserve("key1")
        await store.reserve("key2")
        assert len(store._entries) == 2

        await asyncio.sleep(0.02)
        await store.reserve("key3")

        assert "key3" in store._entries
        assert "key1" not in store._entries
        assert "key2" not in store._entries

    @pytest.mark.asyncio
    async def test_multiple_keys_independent(self) -> None:
        store = _IdempotencyStore(ttl_seconds=10.0)

        result1 = await store.reserve("key1")
        result2 = await store.reserve("key2")
        result1_duplicate = await store.reserve("key1")

        assert result1 is True
        assert result2 is True
        assert result1_duplicate is False


class TestTransportDeliveryService:
    @pytest.mark.asyncio
    async def test_handle_success(
        self,
        mock_settings: Settings,
        mock_connector_manager: ConnectorManager,
        mock_backend_client: WappiBackendClient,
        sample_connector_config: WappiConnectorConfig,
        sample_transport_payload: dict[str, Any],
    ) -> None:
        service = TransportDeliveryService(mock_settings, mock_connector_manager, mock_backend_client)
        mock_connector_manager._connectors["test-connector"] = sample_connector_config

        payload = TransportDeliveryPayload.model_validate(sample_transport_payload)
        headers = {
            "x-service-key": "test-api-key",
            "x-connector-id": "test-connector",
        }

        with patch(
            "wappi_module.transport.service.WappiApiClient.send_message",
            new_callable=AsyncMock,
        ):
            response = await service.handle(payload=payload, headers=headers)

        assert response.status_code == 202
        assert "accepted" in response.body.decode()

    @pytest.mark.asyncio
    async def test_handle_connector_not_found(
        self,
        mock_settings: Settings,
        mock_connector_manager: ConnectorManager,
        mock_backend_client: WappiBackendClient,
        sample_transport_payload: dict[str, Any],
    ) -> None:
        service = TransportDeliveryService(mock_settings, mock_connector_manager, mock_backend_client)

        payload = TransportDeliveryPayload.model_validate(sample_transport_payload)
        headers = {
            "x-service-key": "test-api-key",
            "x-connector-id": "test-connector",
        }

        with pytest.raises(HTTPException) as exc_info:
            await service.handle(payload=payload, headers=headers)

        assert exc_info.value.status_code == 404
        assert "Unknown connector_id" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_handle_missing_service_key(
        self,
        mock_settings: Settings,
        mock_connector_manager: ConnectorManager,
        mock_backend_client: WappiBackendClient,
        sample_connector_config: WappiConnectorConfig,
        sample_transport_payload: dict[str, Any],
    ) -> None:
        service = TransportDeliveryService(mock_settings, mock_connector_manager, mock_backend_client)
        mock_connector_manager._connectors["test-connector"] = sample_connector_config

        payload = TransportDeliveryPayload.model_validate(sample_transport_payload)
        headers = {"x-connector-id": "test-connector"}

        with pytest.raises(HTTPException) as exc_info:
            await service.handle(payload=payload, headers=headers)

        assert exc_info.value.status_code == 401
        assert "Missing service credentials" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_handle_invalid_service_key(
        self,
        mock_settings: Settings,
        mock_connector_manager: ConnectorManager,
        mock_backend_client: WappiBackendClient,
        sample_connector_config: WappiConnectorConfig,
        sample_transport_payload: dict[str, Any],
    ) -> None:
        service = TransportDeliveryService(mock_settings, mock_connector_manager, mock_backend_client)
        mock_connector_manager._connectors["test-connector"] = sample_connector_config

        payload = TransportDeliveryPayload.model_validate(sample_transport_payload)
        headers = {
            "x-service-key": "wrong-key",
            "x-connector-id": "test-connector",
        }

        with pytest.raises(HTTPException) as exc_info:
            await service.handle(payload=payload, headers=headers)

        assert exc_info.value.status_code == 401
        assert "Invalid service credentials" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_handle_missing_connector_header(
        self,
        mock_settings: Settings,
        mock_connector_manager: ConnectorManager,
        mock_backend_client: WappiBackendClient,
        sample_connector_config: WappiConnectorConfig,
        sample_transport_payload: dict[str, Any],
    ) -> None:
        service = TransportDeliveryService(mock_settings, mock_connector_manager, mock_backend_client)
        mock_connector_manager._connectors["test-connector"] = sample_connector_config

        payload = TransportDeliveryPayload.model_validate(sample_transport_payload)
        headers = {"x-service-key": "test-api-key"}

        with pytest.raises(HTTPException) as exc_info:
            await service.handle(payload=payload, headers=headers)

        assert exc_info.value.status_code == 401
        assert "Missing connector header" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_handle_connector_header_mismatch(
        self,
        mock_settings: Settings,
        mock_connector_manager: ConnectorManager,
        mock_backend_client: WappiBackendClient,
        sample_connector_config: WappiConnectorConfig,
        sample_transport_payload: dict[str, Any],
    ) -> None:
        service = TransportDeliveryService(mock_settings, mock_connector_manager, mock_backend_client)
        mock_connector_manager._connectors["test-connector"] = sample_connector_config

        payload = TransportDeliveryPayload.model_validate(sample_transport_payload)
        headers = {
            "x-service-key": "test-api-key",
            "x-connector-id": "wrong-connector",
        }

        with pytest.raises(HTTPException) as exc_info:
            await service.handle(payload=payload, headers=headers)

        assert exc_info.value.status_code == 401
        assert "Connector header mismatch" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_handle_duplicate_correlation_id(
        self,
        mock_settings: Settings,
        mock_connector_manager: ConnectorManager,
        mock_backend_client: WappiBackendClient,
        sample_connector_config: WappiConnectorConfig,
        sample_transport_payload: dict[str, Any],
    ) -> None:
        service = TransportDeliveryService(mock_settings, mock_connector_manager, mock_backend_client)
        mock_connector_manager._connectors["test-connector"] = sample_connector_config

        payload = TransportDeliveryPayload.model_validate(sample_transport_payload)
        headers = {
            "x-service-key": "test-api-key",
            "x-connector-id": "test-connector",
        }

        with patch(
            "wappi_module.transport.service.WappiApiClient.send_message",
            new_callable=AsyncMock,
        ):
            first_response = await service.handle(payload=payload, headers=headers)
            second_response = await service.handle(payload=payload, headers=headers)

        assert first_response.status_code == 202
        assert second_response.status_code == 409
        assert "duplicate" in second_response.body.decode()

    @pytest.mark.asyncio
    async def test_handle_empty_correlation_id(
        self,
        mock_settings: Settings,
        mock_connector_manager: ConnectorManager,
        mock_backend_client: WappiBackendClient,
        sample_connector_config: WappiConnectorConfig,
        sample_transport_payload: dict[str, Any],
    ) -> None:
        service = TransportDeliveryService(mock_settings, mock_connector_manager, mock_backend_client)
        mock_connector_manager._connectors["test-connector"] = sample_connector_config

        sample_transport_payload["correlation_id"] = ""
        payload = TransportDeliveryPayload.model_validate(sample_transport_payload)
        headers = {
            "x-service-key": "test-api-key",
            "x-connector-id": "test-connector",
        }

        with pytest.raises(HTTPException) as exc_info:
            await service.handle(payload=payload, headers=headers)

        assert exc_info.value.status_code == 422
        assert "Correlation id must be provided" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_handle_delivery_failure(
        self,
        mock_settings: Settings,
        mock_connector_manager: ConnectorManager,
        mock_backend_client: WappiBackendClient,
        sample_connector_config: WappiConnectorConfig,
        sample_transport_payload: dict[str, Any],
    ) -> None:
        service = TransportDeliveryService(mock_settings, mock_connector_manager, mock_backend_client)
        mock_connector_manager._connectors["test-connector"] = sample_connector_config

        payload = TransportDeliveryPayload.model_validate(sample_transport_payload)
        headers = {
            "x-service-key": "test-api-key",
            "x-connector-id": "test-connector",
        }

        with patch(
            "wappi_module.transport.service.WappiApiClient.send_message",
            new_callable=AsyncMock,
            side_effect=WappiApiError("API Error"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await service.handle(payload=payload, headers=headers)

        assert exc_info.value.status_code == 502
        assert "Failed to deliver to Wappi" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_deliver_replies_uses_chat_id_from_metadata(
        self,
        mock_settings: Settings,
        mock_connector_manager: ConnectorManager,
        mock_backend_client: WappiBackendClient,
        sample_connector_config: WappiConnectorConfig,
    ) -> None:
        service = TransportDeliveryService(mock_settings, mock_connector_manager, mock_backend_client)

        payload = TransportDeliveryPayload(
            connector_id="test-connector",
            company_id="123",
            channel_type="telegram",
            user_id="user123",
            conversation_id="conv123",
            correlation_id="corr123",
            replies=["Test"],
            metadata={"chat_id": "999888777"},
        )

        mock_send = AsyncMock()
        with patch("wappi_module.transport.service.WappiApiClient.send_message", mock_send):
            await service._deliver_replies(sample_connector_config, payload)

        mock_send.assert_called_once()
        assert mock_send.call_args[1]["recipient"] == "999888777"

    @pytest.mark.asyncio
    async def test_deliver_replies_uses_chat_id_from_extra_metadata(
        self,
        mock_settings: Settings,
        mock_connector_manager: ConnectorManager,
        mock_backend_client: WappiBackendClient,
        sample_connector_config: WappiConnectorConfig,
    ) -> None:
        service = TransportDeliveryService(mock_settings, mock_connector_manager, mock_backend_client)

        payload = TransportDeliveryPayload(
            connector_id="test-connector",
            company_id="123",
            channel_type="telegram",
            user_id="user123",
            conversation_id="conv123",
            correlation_id="corr123",
            replies=["Test"],
            metadata={"extra": {"chat_id": "111222333"}},
        )

        mock_send = AsyncMock()
        with patch("wappi_module.transport.service.WappiApiClient.send_message", mock_send):
            await service._deliver_replies(sample_connector_config, payload)

        mock_send.assert_called_once()
        assert mock_send.call_args[1]["recipient"] == "111222333"

    @pytest.mark.asyncio
    async def test_deliver_replies_fallback_to_conversation_id(
        self,
        mock_settings: Settings,
        mock_connector_manager: ConnectorManager,
        mock_backend_client: WappiBackendClient,
        sample_connector_config: WappiConnectorConfig,
    ) -> None:
        service = TransportDeliveryService(mock_settings, mock_connector_manager, mock_backend_client)

        payload = TransportDeliveryPayload(
            connector_id="test-connector",
            company_id="123",
            channel_type="telegram",
            user_id="user123",
            conversation_id="fallback_conv_id",
            correlation_id="corr123",
            replies=["Test"],
            metadata={},
        )

        mock_send = AsyncMock()
        with patch("wappi_module.transport.service.WappiApiClient.send_message", mock_send):
            await service._deliver_replies(sample_connector_config, payload)

        mock_send.assert_called_once()
        assert mock_send.call_args[1]["recipient"] == "fallback_conv_id"

    @pytest.mark.asyncio
    async def test_deliver_replies_custom_api_base_url(
        self,
        mock_settings: Settings,
        mock_connector_manager: ConnectorManager,
        mock_backend_client: WappiBackendClient,
    ) -> None:
        service = TransportDeliveryService(mock_settings, mock_connector_manager, mock_backend_client)

        connector = WappiConnectorConfig(
            connector_id="test",
            company_id="123",
            wappi_token=SecretStr("token"),
            wappi_profile_id="profile",
            metadata={"api_base_url": "https://custom.wappi.pro"},
        )

        payload = TransportDeliveryPayload(
            connector_id="test",
            company_id="123",
            channel_type="telegram",
            user_id="user123",
            conversation_id="conv123",
            correlation_id="corr123",
            replies=["Test"],
            metadata={"chat_id": "123"},
        )

        mock_send = AsyncMock()
        with patch(
            "wappi_module.transport.service.WappiApiClient.__init__",
            return_value=None,
        ) as mock_init:
            with patch("wappi_module.transport.service.WappiApiClient.send_message", mock_send):
                await service._deliver_replies(connector, payload)

        mock_init.assert_called_once_with(api_base_url="https://custom.wappi.pro")

    @pytest.mark.asyncio
    async def test_deliver_replies_multiple_messages(
        self,
        mock_settings: Settings,
        mock_connector_manager: ConnectorManager,
        mock_backend_client: WappiBackendClient,
        sample_connector_config: WappiConnectorConfig,
    ) -> None:
        service = TransportDeliveryService(mock_settings, mock_connector_manager, mock_backend_client)

        payload = TransportDeliveryPayload(
            connector_id="test-connector",
            company_id="123",
            channel_type="telegram",
            user_id="user123",
            conversation_id="conv123",
            correlation_id="corr123",
            replies=["Message 1", "Message 2", "Message 3"],
            metadata={"chat_id": "123"},
        )

        mock_send = AsyncMock()
        with patch("wappi_module.transport.service.WappiApiClient.send_message", mock_send):
            await service._deliver_replies(sample_connector_config, payload)

        assert mock_send.call_count == 3

    @pytest.mark.asyncio
    async def test_deliver_replies_skips_empty_messages(
        self,
        mock_settings: Settings,
        mock_connector_manager: ConnectorManager,
        mock_backend_client: WappiBackendClient,
        sample_connector_config: WappiConnectorConfig,
    ) -> None:
        service = TransportDeliveryService(mock_settings, mock_connector_manager, mock_backend_client)

        payload = TransportDeliveryPayload(
            connector_id="test-connector",
            company_id="123",
            channel_type="telegram",
            user_id="user123",
            conversation_id="conv123",
            correlation_id="corr123",
            replies=["Message 1", "  ", "Message 2"],
            metadata={"chat_id": "123"},
        )

        mock_send = AsyncMock()
        with patch("wappi_module.transport.service.WappiApiClient.send_message", mock_send):
            await service._deliver_replies(sample_connector_config, payload)

        assert mock_send.call_count == 2

    @pytest.mark.asyncio
    async def test_send_with_retry_success_on_first_attempt(
        self,
        mock_settings: Settings,
        mock_connector_manager: ConnectorManager,
        mock_backend_client: WappiBackendClient,
        sample_connector_config: WappiConnectorConfig,
    ) -> None:
        service = TransportDeliveryService(mock_settings, mock_connector_manager, mock_backend_client)

        payload = TransportDeliveryPayload(
            connector_id="test-connector",
            company_id="123",
            channel_type="telegram",
            user_id="user123",
            conversation_id="conv123",
            correlation_id="corr123",
            replies=["Test"],
            metadata={"chat_id": "123"},
        )

        mock_send = AsyncMock()
        with patch("wappi_module.transport.service.WappiApiClient.send_message", mock_send):
            await service._deliver_replies(sample_connector_config, payload)

        mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_with_retry_rate_limit_429(
        self,
        mock_settings: Settings,
        mock_connector_manager: ConnectorManager,
        mock_backend_client: WappiBackendClient,
        sample_connector_config: WappiConnectorConfig,
    ) -> None:
        service = TransportDeliveryService(mock_settings, mock_connector_manager, mock_backend_client)

        payload = TransportDeliveryPayload(
            connector_id="test-connector",
            company_id="123",
            channel_type="telegram",
            user_id="user123",
            conversation_id="conv123",
            correlation_id="corr123",
            replies=["Test"],
            metadata={"chat_id": "123"},
        )

        mock_send = AsyncMock(
            side_effect=[
                WappiApiError("429 rate limit"),
                None,
            ]
        )

        with patch("wappi_module.transport.service.WappiApiClient.send_message", mock_send):
            await service._deliver_replies(sample_connector_config, payload)

        assert mock_send.call_count == 2

    @pytest.mark.asyncio
    async def test_send_with_retry_400_error_fails_immediately(
        self,
        mock_settings: Settings,
        mock_connector_manager: ConnectorManager,
        mock_backend_client: WappiBackendClient,
        sample_connector_config: WappiConnectorConfig,
    ) -> None:
        service = TransportDeliveryService(mock_settings, mock_connector_manager, mock_backend_client)

        payload = TransportDeliveryPayload(
            connector_id="test-connector",
            company_id="123",
            channel_type="telegram",
            user_id="user123",
            conversation_id="conv123",
            correlation_id="corr123",
            replies=["Test"],
            metadata={"chat_id": "123"},
        )

        mock_send = AsyncMock(side_effect=WappiApiError("400 bad request"))

        with patch("wappi_module.transport.service.WappiApiClient.send_message", mock_send):
            with pytest.raises(TransportDeliveryError):
                await service._deliver_replies(sample_connector_config, payload)

        assert mock_send.call_count == 1

    @pytest.mark.asyncio
    async def test_send_with_retry_exceeds_max_attempts(
        self,
        mock_connector_manager: ConnectorManager,
        mock_backend_client: WappiBackendClient,
        sample_connector_config: WappiConnectorConfig,
    ) -> None:
        from common.config import EventingSettings

        settings = Settings(
            backend_url="http://backend.test",
            sales_agent_url="http://sales-agent.test",
            service_api_key="test-key",  # pragma: allowlist secret
            max_delivery_attempts=2,
            eventing=EventingSettings(enabled=False),
        )
        service = TransportDeliveryService(settings, mock_connector_manager, mock_backend_client)

        payload = TransportDeliveryPayload(
            connector_id="test-connector",
            company_id="123",
            channel_type="telegram",
            user_id="user123",
            conversation_id="conv123",
            correlation_id="corr123",
            replies=["Test"],
            metadata={"chat_id": "123"},
        )

        mock_send = AsyncMock(side_effect=WappiApiError("500 server error"))

        with patch("wappi_module.transport.service.WappiApiClient.send_message", mock_send):
            with pytest.raises(TransportDeliveryError):
                await service._deliver_replies(sample_connector_config, payload)

        assert mock_send.call_count == 2

    @pytest.mark.asyncio
    async def test_init_requires_api_key(
        self,
        mock_connector_manager: ConnectorManager,
        mock_backend_client: WappiBackendClient,
    ) -> None:
        from common.config import EventingSettings, ServiceAuthSettings

        settings = Settings(
            backend_url="http://backend.test",
            sales_agent_url="http://sales-agent.test",
            service=ServiceAuthSettings(api_key=None),
            eventing=EventingSettings(enabled=False),
        )

        with pytest.raises(RuntimeError, match="SERVICE__API_KEY must be configured"):
            TransportDeliveryService(settings, mock_connector_manager, mock_backend_client)
