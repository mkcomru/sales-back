"""Additional edge case tests for TransportDeliveryService."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from pydantic import SecretStr

from common.config import BackendSettings, EventingSettings, S3Settings
from wappi_module.config import Settings
from wappi_module.connectors.manager import ConnectorManager
from wappi_module.connectors.models import WappiConnectorConfig
from wappi_module.services.backend import WappiBackendClient
from wappi_module.services.wappi_api import WappiApiError
from wappi_module.transport.models import TransportDeliveryPayload
from wappi_module.transport.service import TransportDeliveryService


class TestTransportDeliveryServiceEdgeCases:
    @pytest.mark.asyncio
    async def test_send_with_retry_unexpected_exception(
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

        mock_send = AsyncMock(side_effect=ValueError("Unexpected error"))

        with patch("wappi_module.transport.service.WappiApiClient.send_message", mock_send):
            with pytest.raises(Exception, match="Unexpected Wappi error"):
                await service._deliver_replies(sample_connector_config, payload)

        assert mock_send.call_count == 1

    @pytest.mark.asyncio
    async def test_send_with_retry_delay_calculation_rate_limit(
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
                WappiApiError("429 rate limit"),
                None,
            ]
        )

        sleep_mock = AsyncMock()
        with patch("wappi_module.transport.service.WappiApiClient.send_message", mock_send):
            with patch("asyncio.sleep", sleep_mock):
                await service._deliver_replies(sample_connector_config, payload)

        assert mock_send.call_count == 3
        assert sleep_mock.call_count == 2
        assert sleep_mock.call_args_list[0][0][0] == 5.0
        assert sleep_mock.call_args_list[1][0][0] == 10.0

    @pytest.mark.asyncio
    async def test_send_with_retry_delay_calculation_max_delay(
        self,
        mock_connector_manager: ConnectorManager,
        mock_backend_client: WappiBackendClient,
        sample_connector_config: WappiConnectorConfig,
    ) -> None:
        settings = Settings(
            backend=BackendSettings(url="http://backend.test/api/v1"),
            service_api_key="test-key",  # pragma: allowlist secret
            max_delivery_attempts=5,
            eventing=EventingSettings(enabled=False),
            s3=S3Settings(
                endpoint_url="http://localhost:9000",
                access_key_id=SecretStr("test-access-key"),  # pragma: allowlist secret
                secret_access_key=SecretStr("test-secret-key"),  # pragma: allowlist secret
                bucket_name="test-bucket",
            ),
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

        mock_send = AsyncMock(
            side_effect=[
                WappiApiError("500 server error"),
                WappiApiError("500 server error"),
                WappiApiError("500 server error"),
                WappiApiError("500 server error"),
                None,
            ]
        )

        sleep_mock = AsyncMock()
        with patch("wappi_module.transport.service.WappiApiClient.send_message", mock_send):
            with patch("asyncio.sleep", sleep_mock):
                await service._deliver_replies(sample_connector_config, payload)

        assert mock_send.call_count == 5
        delays = [call[0][0] for call in sleep_mock.call_args_list]
        assert all(delay <= 30.0 for delay in delays)
        assert max(delays) == 20.0

    @pytest.mark.asyncio
    async def test_deliver_replies_metadata_chat_id_none(
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
            conversation_id="fallback_conv",
            correlation_id="corr123",
            replies=["Test"],
            metadata={"chat_id": None},
        )

        mock_send = AsyncMock()
        with patch("wappi_module.transport.service.WappiApiClient.send_message", mock_send):
            await service._deliver_replies(sample_connector_config, payload)

        mock_send.assert_called_once()
        assert mock_send.call_args[1]["recipient"] == "fallback_conv"

    @pytest.mark.asyncio
    async def test_deliver_replies_extra_not_mapping(
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
            conversation_id="fallback_conv",
            correlation_id="corr123",
            replies=["Test"],
            metadata={"extra": "not a dict"},
        )

        mock_send = AsyncMock()
        with patch("wappi_module.transport.service.WappiApiClient.send_message", mock_send):
            await service._deliver_replies(sample_connector_config, payload)

        mock_send.assert_called_once()
        assert mock_send.call_args[1]["recipient"] == "fallback_conv"

    @pytest.mark.asyncio
    async def test_deliver_replies_extra_chat_id_none(
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
            conversation_id="fallback_conv",
            correlation_id="corr123",
            replies=["Test"],
            metadata={"extra": {"chat_id": None}},
        )

        mock_send = AsyncMock()
        with patch("wappi_module.transport.service.WappiApiClient.send_message", mock_send):
            await service._deliver_replies(sample_connector_config, payload)

        mock_send.assert_called_once()
        assert mock_send.call_args[1]["recipient"] == "fallback_conv"

    @pytest.mark.asyncio
    async def test_handle_correlation_id_with_whitespace(
        self,
        mock_settings: Settings,
        mock_connector_manager: ConnectorManager,
        mock_backend_client: WappiBackendClient,
        sample_connector_config: WappiConnectorConfig,
    ) -> None:
        service = TransportDeliveryService(mock_settings, mock_connector_manager, mock_backend_client)
        mock_connector_manager._connectors["test-connector"] = sample_connector_config

        payload = TransportDeliveryPayload(
            connector_id="test-connector",
            company_id="123",
            channel_type="telegram",
            user_id="user123",
            conversation_id="conv123",
            correlation_id="  corr123  ",
            replies=["Test"],
            metadata={"chat_id": "123"},
        )

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
