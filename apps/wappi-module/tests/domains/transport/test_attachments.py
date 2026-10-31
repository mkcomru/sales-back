"""Tests for attachment delivery in TransportDeliveryService."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from common.models.transport import AttachmentDescriptor
from common.transport.base_backend_client import TransportBackendClientError
from wappi_module.config import Settings
from wappi_module.connectors.manager import ConnectorManager
from wappi_module.connectors.models import WappiConnectorConfig
from wappi_module.services.backend import WappiBackendClient
from wappi_module.services.wappi_api import WappiApiClient, WappiApiError
from wappi_module.transport.service import TransportDeliveryError, TransportDeliveryService


class TestDeliverAttachment:
    @pytest.mark.asyncio
    async def test_deliver_image_attachment(
        self,
        mock_settings: Settings,
        mock_connector_manager: ConnectorManager,
        mock_backend_client: WappiBackendClient,
        sample_connector_config: WappiConnectorConfig,
    ) -> None:
        from common.models.transport import TransportDeliveryPayload

        service = TransportDeliveryService(mock_settings, mock_connector_manager, mock_backend_client)
        file_bytes = b"fake_image_bytes"
        mock_backend_client.download_artifact = AsyncMock(return_value=file_bytes)

        payload = TransportDeliveryPayload(
            connector_id="test-connector",
            company_id="123",
            channel_type="telegram",
            user_id="user123",
            conversation_id="conv123",
            correlation_id="corr123",
            attachments=[
                AttachmentDescriptor(
                    artifact_id="art-001",
                    type="image",
                    mime_type="image/jpeg",
                    caption="A photo",
                )
            ],
        )

        send_image_mock = AsyncMock(return_value={"status": "sent"})
        with patch.object(WappiApiClient, "send_image", send_image_mock):
            await service._deliver_replies(sample_connector_config, payload)

        send_image_mock.assert_called_once()
        call_kwargs = send_image_mock.call_args[1]
        assert call_kwargs["file_bytes"] == file_bytes
        assert call_kwargs["caption"] == "A photo"
        assert call_kwargs["channel_type"] == "telegram"

    @pytest.mark.asyncio
    async def test_deliver_audio_attachment(
        self,
        mock_settings: Settings,
        mock_connector_manager: ConnectorManager,
        mock_backend_client: WappiBackendClient,
        sample_connector_config: WappiConnectorConfig,
    ) -> None:
        from common.models.transport import TransportDeliveryPayload

        service = TransportDeliveryService(mock_settings, mock_connector_manager, mock_backend_client)
        file_bytes = b"fake_audio_bytes"
        mock_backend_client.download_artifact = AsyncMock(return_value=file_bytes)

        payload = TransportDeliveryPayload(
            connector_id="test-connector",
            company_id="123",
            channel_type="telegram",
            user_id="user123",
            conversation_id="conv123",
            correlation_id="corr123",
            attachments=[
                AttachmentDescriptor(
                    artifact_id="art-002",
                    type="audio",
                    mime_type="audio/mpeg",
                )
            ],
        )

        send_audio_mock = AsyncMock(return_value={"status": "sent"})
        with patch.object(WappiApiClient, "send_audio", send_audio_mock):
            await service._deliver_replies(sample_connector_config, payload)

        send_audio_mock.assert_called_once()
        call_kwargs = send_audio_mock.call_args[1]
        assert call_kwargs["file_bytes"] == file_bytes
        assert call_kwargs["caption"] is None

    @pytest.mark.asyncio
    async def test_deliver_document_attachment(
        self,
        mock_settings: Settings,
        mock_connector_manager: ConnectorManager,
        mock_backend_client: WappiBackendClient,
        sample_connector_config: WappiConnectorConfig,
    ) -> None:
        from common.models.transport import TransportDeliveryPayload

        service = TransportDeliveryService(mock_settings, mock_connector_manager, mock_backend_client)
        file_bytes = b"fake_pdf_bytes"
        mock_backend_client.download_artifact = AsyncMock(return_value=file_bytes)

        payload = TransportDeliveryPayload(
            connector_id="test-connector",
            company_id="123",
            channel_type="whatsapp",
            user_id="user123",
            conversation_id="conv123",
            correlation_id="corr123",
            attachments=[
                AttachmentDescriptor(
                    artifact_id="art-003",
                    type="document",
                    mime_type="application/pdf",
                    caption="Report",
                )
            ],
        )

        send_document_mock = AsyncMock(return_value={"status": "sent"})
        with patch.object(WappiApiClient, "send_document", send_document_mock):
            await service._deliver_replies(sample_connector_config, payload)

        send_document_mock.assert_called_once()
        call_kwargs = send_document_mock.call_args[1]
        assert call_kwargs["file_bytes"] == file_bytes
        assert call_kwargs["caption"] == "Report"
        assert "filename" in call_kwargs

    @pytest.mark.asyncio
    async def test_deliver_attachment_download_failure(
        self,
        mock_settings: Settings,
        mock_connector_manager: ConnectorManager,
        mock_backend_client: WappiBackendClient,
        sample_connector_config: WappiConnectorConfig,
    ) -> None:
        from common.models.transport import TransportDeliveryPayload

        service = TransportDeliveryService(mock_settings, mock_connector_manager, mock_backend_client)
        mock_backend_client.download_artifact = AsyncMock(side_effect=TransportBackendClientError("S3 unavailable"))

        payload = TransportDeliveryPayload(
            connector_id="test-connector",
            company_id="123",
            channel_type="telegram",
            user_id="user123",
            conversation_id="conv123",
            correlation_id="corr123",
            attachments=[
                AttachmentDescriptor(
                    artifact_id="art-fail",
                    type="image",
                    mime_type="image/png",
                )
            ],
        )

        with pytest.raises(TransportDeliveryError, match="Failed to download artifact art-fail"):
            await service._deliver_replies(sample_connector_config, payload)

    @pytest.mark.asyncio
    async def test_deliver_attachment_unsupported_type(
        self,
        mock_settings: Settings,
        mock_connector_manager: ConnectorManager,
        mock_backend_client: WappiBackendClient,
        sample_connector_config: WappiConnectorConfig,
    ) -> None:
        from common.models.transport import TransportDeliveryPayload

        service = TransportDeliveryService(mock_settings, mock_connector_manager, mock_backend_client)
        mock_backend_client.download_artifact = AsyncMock(return_value=b"bytes")

        attachment = AttachmentDescriptor.model_construct(
            artifact_id="art-unknown",
            type="sticker",
            mime_type="image/webp",
        )

        payload = TransportDeliveryPayload(
            connector_id="test-connector",
            company_id="123",
            channel_type="telegram",
            user_id="user123",
            conversation_id="conv123",
            correlation_id="corr123",
            attachments=[attachment],
        )

        with pytest.raises(TransportDeliveryError, match="Unsupported attachment type for Wappi"):
            await service._deliver_replies(sample_connector_config, payload)

    @pytest.mark.asyncio
    async def test_deliver_attachment_wappi_400_raises(
        self,
        mock_settings: Settings,
        mock_connector_manager: ConnectorManager,
        mock_backend_client: WappiBackendClient,
        sample_connector_config: WappiConnectorConfig,
    ) -> None:
        from common.models.transport import TransportDeliveryPayload

        service = TransportDeliveryService(mock_settings, mock_connector_manager, mock_backend_client)
        mock_backend_client.download_artifact = AsyncMock(return_value=b"img_bytes")

        payload = TransportDeliveryPayload(
            connector_id="test-connector",
            company_id="123",
            channel_type="telegram",
            user_id="user123",
            conversation_id="conv123",
            correlation_id="corr123",
            attachments=[
                AttachmentDescriptor(
                    artifact_id="art-400",
                    type="image",
                    mime_type="image/jpeg",
                )
            ],
        )

        send_image_mock = AsyncMock(side_effect=WappiApiError("400 bad request"))
        with patch.object(WappiApiClient, "send_image", send_image_mock):
            with pytest.raises(TransportDeliveryError, match="Wappi API rejected attachment"):
                await service._deliver_replies(sample_connector_config, payload)

    @pytest.mark.asyncio
    async def test_deliver_attachment_retries_on_rate_limit(
        self,
        mock_settings: Settings,
        mock_connector_manager: ConnectorManager,
        mock_backend_client: WappiBackendClient,
        sample_connector_config: WappiConnectorConfig,
    ) -> None:
        from common.models.transport import TransportDeliveryPayload

        service = TransportDeliveryService(mock_settings, mock_connector_manager, mock_backend_client)
        mock_backend_client.download_artifact = AsyncMock(return_value=b"img_bytes")

        payload = TransportDeliveryPayload(
            connector_id="test-connector",
            company_id="123",
            channel_type="telegram",
            user_id="user123",
            conversation_id="conv123",
            correlation_id="corr123",
            attachments=[
                AttachmentDescriptor(
                    artifact_id="art-rate",
                    type="image",
                    mime_type="image/jpeg",
                )
            ],
        )

        send_image_mock = AsyncMock(side_effect=[WappiApiError("429 rate limit"), {"status": "sent"}])
        sleep_mock = AsyncMock()
        with patch.object(WappiApiClient, "send_image", send_image_mock):
            with patch("asyncio.sleep", sleep_mock):
                await service._deliver_replies(sample_connector_config, payload)

        assert send_image_mock.call_count == 2
        sleep_mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_deliver_attachment_exceeds_retry_limit(
        self,
        mock_settings: Settings,
        mock_connector_manager: ConnectorManager,
        mock_backend_client: WappiBackendClient,
        sample_connector_config: WappiConnectorConfig,
    ) -> None:
        from common.models.transport import TransportDeliveryPayload

        service = TransportDeliveryService(mock_settings, mock_connector_manager, mock_backend_client)
        mock_backend_client.download_artifact = AsyncMock(return_value=b"img_bytes")

        payload = TransportDeliveryPayload(
            connector_id="test-connector",
            company_id="123",
            channel_type="telegram",
            user_id="user123",
            conversation_id="conv123",
            correlation_id="corr123",
            attachments=[
                AttachmentDescriptor(
                    artifact_id="art-retry",
                    type="image",
                    mime_type="image/jpeg",
                )
            ],
        )

        # max_delivery_attempts=3 in mock_settings
        send_image_mock = AsyncMock(side_effect=WappiApiError("500 server error"))
        with patch.object(WappiApiClient, "send_image", send_image_mock):
            with pytest.raises(TransportDeliveryError, match="Exceeded attachment delivery retry limit"):
                await service._deliver_replies(sample_connector_config, payload)

        assert send_image_mock.call_count == 3

    @pytest.mark.asyncio
    async def test_deliver_text_and_attachment_together(
        self,
        mock_settings: Settings,
        mock_connector_manager: ConnectorManager,
        mock_backend_client: WappiBackendClient,
        sample_connector_config: WappiConnectorConfig,
    ) -> None:
        from common.models.transport import TransportDeliveryPayload

        service = TransportDeliveryService(mock_settings, mock_connector_manager, mock_backend_client)
        mock_backend_client.download_artifact = AsyncMock(return_value=b"img_bytes")

        payload = TransportDeliveryPayload(
            connector_id="test-connector",
            company_id="123",
            channel_type="telegram",
            user_id="user123",
            conversation_id="conv123",
            correlation_id="corr123",
            replies=["Here is your image:"],
            metadata={"chat_id": "999"},
            attachments=[
                AttachmentDescriptor(
                    artifact_id="art-combined",
                    type="image",
                    mime_type="image/png",
                )
            ],
        )

        send_message_mock = AsyncMock(return_value={"status": "sent"})
        send_image_mock = AsyncMock(return_value={"status": "sent"})
        with patch.object(WappiApiClient, "send_message", send_message_mock):
            with patch.object(WappiApiClient, "send_image", send_image_mock):
                await service._deliver_replies(sample_connector_config, payload)

        send_message_mock.assert_called_once()
        send_image_mock.assert_called_once()
