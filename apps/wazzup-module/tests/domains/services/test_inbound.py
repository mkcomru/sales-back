from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from common import MessageRole
from wazzup_module.connectors.models import WazzupConnectorConfig
from wazzup_module.services.inbound import BackendInboundClient, _as_str, _parse_ts


class TestAsStr:
    def test_returns_string(self) -> None:
        assert _as_str("hello") == "hello"

    def test_strips_whitespace(self) -> None:
        assert _as_str("  hello  ") == "hello"

    def test_none_returns_none(self) -> None:
        assert _as_str(None) is None

    def test_empty_string_returns_none(self) -> None:
        assert _as_str("") is None

    def test_whitespace_only_returns_none(self) -> None:
        assert _as_str("   ") is None

    def test_integer_converted(self) -> None:
        assert _as_str(123) == "123"


class TestParseTs:
    def test_valid_iso_timestamp(self) -> None:
        ts = _parse_ts("2026-03-19T12:00:00.000Z")
        assert isinstance(ts, float)
        assert ts > 0

    def test_none_returns_current_time(self) -> None:
        ts = _parse_ts(None)
        assert isinstance(ts, float)
        assert ts > 0

    def test_empty_string_returns_current_time(self) -> None:
        ts = _parse_ts("")
        assert isinstance(ts, float)

    def test_invalid_format_returns_current_time(self) -> None:
        ts = _parse_ts("not-a-date")
        assert isinstance(ts, float)


def _base_message(**overrides: Any) -> dict[str, Any]:
    msg: dict[str, Any] = {
        "messageId": "msg-123",
        "channelId": "chan-1",
        "chatType": "instagram",
        "chatId": "user-1",
        "dateTime": "2026-03-19T12:00:00.000Z",
        "type": "text",
        "isEcho": False,
        "text": "Hello",
        "contact": {"name": "Test User", "username": "testuser"},
        "status": "inbound",
    }
    msg.update(overrides)
    return msg


class TestNormalizeMessage:
    @pytest.mark.anyio
    async def test_user_message(self, mock_inbound_client: BackendInboundClient, sample_connector_config: Any) -> None:
        msg = _base_message()
        envelope = await mock_inbound_client._normalize_message(msg, sample_connector_config)
        assert envelope is not None
        assert envelope.role == MessageRole.USER
        assert envelope.text == "Hello"
        assert envelope.conversation_id == "user-1"
        assert envelope.user_id == "user-1"
        assert envelope.sender_name == "Test User"
        assert envelope.sender_username == "testuser"
        assert envelope.message_id == "msg-123"
        assert envelope.extra == {}

    @pytest.mark.anyio
    async def test_manager_message(
        self, mock_inbound_client: BackendInboundClient, sample_connector_config: Any
    ) -> None:
        msg = _base_message(isEcho=True, sentFromApp=True)
        envelope = await mock_inbound_client._normalize_message(msg, sample_connector_config)
        assert envelope is not None
        assert envelope.role == MessageRole.MANAGER
        assert envelope.extra == {"_manager_outgoing": True}

    @pytest.mark.anyio
    async def test_echo_not_from_app_skipped(
        self, mock_inbound_client: BackendInboundClient, sample_connector_config: Any
    ) -> None:
        msg = _base_message(isEcho=True, sentFromApp=False)
        assert await mock_inbound_client._normalize_message(msg, sample_connector_config) is None

    @pytest.mark.anyio
    async def test_deleted_message_skipped(
        self, mock_inbound_client: BackendInboundClient, sample_connector_config: Any
    ) -> None:
        msg = _base_message(isDeleted=True)
        assert await mock_inbound_client._normalize_message(msg, sample_connector_config) is None

    @pytest.mark.anyio
    async def test_edited_message_skipped(
        self, mock_inbound_client: BackendInboundClient, sample_connector_config: Any
    ) -> None:
        msg = _base_message(isEdited=True)
        assert await mock_inbound_client._normalize_message(msg, sample_connector_config) is None

    @pytest.mark.anyio
    async def test_no_chat_id_skipped(
        self, mock_inbound_client: BackendInboundClient, sample_connector_config: Any
    ) -> None:
        msg = _base_message(chatId=None)
        assert await mock_inbound_client._normalize_message(msg, sample_connector_config) is None

    @pytest.mark.anyio
    async def test_empty_text_skipped(
        self, mock_inbound_client: BackendInboundClient, sample_connector_config: Any
    ) -> None:
        msg = _base_message(text="")
        assert await mock_inbound_client._normalize_message(msg, sample_connector_config) is None

    @pytest.mark.anyio
    async def test_no_text_skipped(
        self, mock_inbound_client: BackendInboundClient, sample_connector_config: Any
    ) -> None:
        msg = _base_message(text=None)
        assert await mock_inbound_client._normalize_message(msg, sample_connector_config) is None

    @pytest.mark.anyio
    async def test_no_contact_still_works(
        self, mock_inbound_client: BackendInboundClient, sample_connector_config: Any
    ) -> None:
        msg = _base_message()
        del msg["contact"]
        envelope = await mock_inbound_client._normalize_message(msg, sample_connector_config)
        assert envelope is not None
        assert envelope.sender_name is None
        assert envelope.sender_username is None

    @pytest.mark.anyio
    async def test_contact_with_phone(
        self, mock_inbound_client: BackendInboundClient, sample_connector_config: Any
    ) -> None:
        msg = _base_message(contact={"name": "User", "phone": "+79001234567"})
        envelope = await mock_inbound_client._normalize_message(msg, sample_connector_config)
        assert envelope is not None
        assert envelope.sender_phone == "+79001234567"


class TestAudioMessage:
    @pytest.mark.anyio
    async def test_audio_with_content_uri(
        self, mock_inbound_client: BackendInboundClient, sample_connector_config: WazzupConnectorConfig
    ) -> None:
        msg = _base_message(type="audio", text=None, contentUri="https://cdn.wazzup.test/audio.ogg")
        with patch.object(mock_inbound_client, "_process_audio", new_callable=AsyncMock, return_value=["artifact-1"]):
            envelope = await mock_inbound_client._normalize_message(msg, sample_connector_config)
        assert envelope is not None
        assert envelope.text is None
        assert envelope.artifact_ids == ["artifact-1"]
        assert envelope.audio is None

    @pytest.mark.anyio
    async def test_audio_without_content_uri_skipped(
        self, mock_inbound_client: BackendInboundClient, sample_connector_config: WazzupConnectorConfig
    ) -> None:
        msg = _base_message(type="audio", text=None)
        del msg["text"]
        envelope = await mock_inbound_client._normalize_message(msg, sample_connector_config)
        assert envelope is None

    @pytest.mark.anyio
    async def test_audio_download_error_returns_empty_artifact_ids(
        self, mock_inbound_client: BackendInboundClient, sample_connector_config: WazzupConnectorConfig
    ) -> None:
        mock_inbound_client._audio_converter = MagicMock()
        msg = _base_message(type="audio", text=None, contentUri="https://cdn.wazzup.test/audio.ogg")
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.__aenter__.return_value.get = AsyncMock(side_effect=Exception("network error"))
            envelope = await mock_inbound_client._normalize_message(msg, sample_connector_config)
        assert envelope is not None
        assert envelope.artifact_ids == []

    @pytest.mark.anyio
    async def test_audio_upload_error_returns_empty_artifact_ids(
        self, mock_inbound_client: BackendInboundClient, sample_connector_config: WazzupConnectorConfig
    ) -> None:
        audio_converter = MagicMock()
        audio_converter.convert_to_mp3 = AsyncMock(return_value=b"mp3data")
        mock_inbound_client._audio_converter = audio_converter

        msg = _base_message(type="audio", text=None, contentUri="https://cdn.wazzup.test/audio.ogg")

        mock_response = MagicMock()
        mock_response.content = b"oggdata"
        mock_response.headers = {"content-type": "audio/ogg"}
        mock_response.raise_for_status = MagicMock()

        with (
            patch("httpx.AsyncClient") as mock_client_cls,
            patch.object(
                mock_inbound_client._backend_client,
                "upload_artifact",
                new_callable=AsyncMock,
                side_effect=Exception("upload failed"),
            ),
        ):
            mock_client_cls.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
            envelope = await mock_inbound_client._normalize_message(msg, sample_connector_config)

        assert envelope is not None
        assert envelope.artifact_ids == []

    @pytest.mark.anyio
    async def test_audio_converter_none_returns_empty_artifact_ids(
        self, mock_inbound_client: BackendInboundClient, sample_connector_config: WazzupConnectorConfig
    ) -> None:
        mock_inbound_client._audio_converter = None
        msg = _base_message(type="audio", text=None, contentUri="https://cdn.wazzup.test/audio.ogg")
        envelope = await mock_inbound_client._normalize_message(msg, sample_connector_config)
        assert envelope is not None
        assert envelope.artifact_ids == []


class TestForwardMessage:
    @pytest.mark.anyio
    async def test_forward_calls_send_envelope(
        self, mock_inbound_client: BackendInboundClient, sample_connector_config: Any
    ) -> None:
        msg = _base_message()
        with patch.object(mock_inbound_client, "_send_envelope", new_callable=AsyncMock) as mock_send:
            await mock_inbound_client.forward_message("c1", sample_connector_config, msg)
        mock_send.assert_called_once()

    @pytest.mark.anyio
    async def test_forward_skips_when_normalize_returns_none(
        self, mock_inbound_client: BackendInboundClient, sample_connector_config: Any
    ) -> None:
        msg = _base_message(isDeleted=True)
        with patch.object(mock_inbound_client, "_send_envelope", new_callable=AsyncMock) as mock_send:
            await mock_inbound_client.forward_message("c1", sample_connector_config, msg)
        mock_send.assert_not_called()
