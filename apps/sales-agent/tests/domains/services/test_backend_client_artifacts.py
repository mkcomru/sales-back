"""Tests for BackendClient artifact and transcription methods."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from common import SalesAgentSettings

from src.sales_agent.services.backend_client import BackendClient


class TestDownloadArtifact:
    """Tests for BackendClient.download_artifact method."""

    @pytest.mark.asyncio
    async def test_download_artifact_success(self, settings: SalesAgentSettings) -> None:
        """Test successful artifact download."""
        settings.backend.url = "http://localhost:8001"
        client = BackendClient(settings)

        artifact_id = "company_1/voice/test.mp3"
        file_bytes = b"fake audio content"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = file_bytes
        mock_response.raise_for_status = MagicMock()

        mock_chat_client = AsyncMock()
        mock_chat_client.get = AsyncMock(return_value=mock_response)
        client._chat_client = mock_chat_client

        result = await client.download_artifact(artifact_id)

        assert result == file_bytes
        assert mock_chat_client.get.called
        call_args = mock_chat_client.get.call_args[0]
        assert f"/internal/artifacts/{artifact_id}" in call_args[0]

    @pytest.mark.asyncio
    async def test_download_artifact_not_found(self, settings: SalesAgentSettings) -> None:
        """Test artifact download when artifact doesn't exist."""
        settings.backend.url = "http://localhost:8001"
        client = BackendClient(settings)

        artifact_id = "company_1/voice/nonexistent.mp3"

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Not found", request=MagicMock(), response=mock_response
        )

        mock_chat_client = AsyncMock()
        mock_chat_client.get = AsyncMock(return_value=mock_response)
        client._chat_client = mock_chat_client

        with pytest.raises(httpx.HTTPStatusError):
            await client.download_artifact(artifact_id)

    @pytest.mark.asyncio
    async def test_download_artifact_http_error(self, settings: SalesAgentSettings) -> None:
        """Test artifact download when HTTP request fails."""
        settings.backend.url = "http://localhost:8001"
        client = BackendClient(settings)

        artifact_id = "company_1/voice/test.mp3"

        mock_chat_client = AsyncMock()
        mock_chat_client.get = AsyncMock(side_effect=httpx.HTTPError("Connection error"))
        client._chat_client = mock_chat_client

        with pytest.raises(httpx.HTTPError):
            await client.download_artifact(artifact_id)

    @pytest.mark.asyncio
    async def test_download_artifact_different_types(self, settings: SalesAgentSettings) -> None:
        """Test artifact download for different file types."""
        settings.backend.url = "http://localhost:8001"
        client = BackendClient(settings)

        test_cases = [
            ("company_1/voice/test.mp3", b"audio content"),
            ("company_1/image/test.jpg", b"image content"),
            ("company_1/video/test.mp4", b"video content"),
            ("company_1/document/test.pdf", b"pdf content"),
        ]

        for artifact_id, expected_content in test_cases:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.content = expected_content
            mock_response.raise_for_status = MagicMock()

            mock_chat_client = AsyncMock()
            mock_chat_client.get = AsyncMock(return_value=mock_response)
            client._chat_client = mock_chat_client

            result = await client.download_artifact(artifact_id)

            assert result == expected_content


class TestGetMessageById:
    """Tests for BackendClient.get_message_by_id method."""

    @pytest.mark.asyncio
    async def test_get_message_by_id_success(self, settings: SalesAgentSettings) -> None:
        """Test successful message retrieval."""
        settings.backend.url = "http://localhost:8001"
        client = BackendClient(settings)

        message_id = "msg-123"
        message_data = {
            "message_id": message_id,
            "thread_id": "thread-123",
            "role": "user",
            "content": "Hello",
            "type": "text",
            "artifact_ids": ["company_1/voice/test.mp3"],
            "created_at": "2025-01-01T00:00:00Z",
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = message_data
        mock_response.raise_for_status = MagicMock()

        mock_chat_client = AsyncMock()
        mock_chat_client.get = AsyncMock(return_value=mock_response)
        client._chat_client = mock_chat_client

        result = await client.get_message_by_id(message_id)

        assert result == message_data
        assert result["message_id"] == message_id
        assert result["artifact_ids"] == ["company_1/voice/test.mp3"]
        assert mock_chat_client.get.called
        call_args = mock_chat_client.get.call_args[0]
        assert f"/internal/chat/messages/{message_id}" in call_args[0]

    @pytest.mark.asyncio
    async def test_get_message_by_id_with_transcription(self, settings: SalesAgentSettings) -> None:
        """Test message retrieval with cached transcription."""
        settings.backend.url = "http://localhost:8001"
        client = BackendClient(settings)

        message_id = "msg-456"
        message_data = {
            "message_id": message_id,
            "thread_id": "thread-456",
            "role": "user",
            "content": "",
            "transcription": "This is transcribed text",
            "type": "audio",
            "artifact_ids": ["company_1/voice/audio.mp3"],
            "created_at": "2025-01-01T00:00:00Z",
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = message_data
        mock_response.raise_for_status = MagicMock()

        mock_chat_client = AsyncMock()
        mock_chat_client.get = AsyncMock(return_value=mock_response)
        client._chat_client = mock_chat_client

        result = await client.get_message_by_id(message_id)

        assert result["content"] == ""
        assert result["transcription"] == "This is transcribed text"
        assert result["type"] == "audio"

    @pytest.mark.asyncio
    async def test_get_message_by_id_not_found(self, settings: SalesAgentSettings) -> None:
        """Test message retrieval when message doesn't exist."""
        settings.backend.url = "http://localhost:8001"
        client = BackendClient(settings)

        message_id = "nonexistent-msg-id"

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Not found", request=MagicMock(), response=mock_response
        )

        mock_chat_client = AsyncMock()
        mock_chat_client.get = AsyncMock(return_value=mock_response)
        client._chat_client = mock_chat_client

        with pytest.raises(httpx.HTTPStatusError):
            await client.get_message_by_id(message_id)

    @pytest.mark.asyncio
    async def test_get_message_by_id_empty_artifact_ids(self, settings: SalesAgentSettings) -> None:
        """Test message retrieval with empty artifact_ids."""
        settings.backend.url = "http://localhost:8001"
        client = BackendClient(settings)

        message_id = "msg-empty"
        message_data = {
            "message_id": message_id,
            "thread_id": "thread-empty",
            "role": "user",
            "content": "Text message",
            "type": "text",
            "artifact_ids": [],
            "created_at": "2025-01-01T00:00:00Z",
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = message_data
        mock_response.raise_for_status = MagicMock()

        mock_chat_client = AsyncMock()
        mock_chat_client.get = AsyncMock(return_value=mock_response)
        client._chat_client = mock_chat_client

        result = await client.get_message_by_id(message_id)

        assert result["artifact_ids"] == []


class TestSaveTranscription:
    """Tests for BackendClient.save_transcription method."""

    @pytest.mark.asyncio
    async def test_save_transcription_success(self, settings: SalesAgentSettings) -> None:
        """Test successful transcription save."""
        settings.backend.url = "http://localhost:8001"
        client = BackendClient(settings)

        message_id = "msg-123"
        transcribed_text = "This is the transcribed text"
        response_data = {
            "message_id": message_id,
            "thread_id": "thread-123",
            "role": "user",
            "content": "",
            "transcription": transcribed_text,
            "type": "audio",
            "artifact_ids": ["company_1/voice/audio.mp3"],
            "created_at": "2025-01-01T00:00:00Z",
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = response_data
        mock_response.raise_for_status = MagicMock()

        mock_chat_client = AsyncMock()
        mock_chat_client.post = AsyncMock(return_value=mock_response)
        client._chat_client = mock_chat_client

        result = await client.save_transcription(message_id, transcribed_text)

        assert result == response_data
        assert result["transcription"] == transcribed_text
        assert result["content"] == ""
        assert mock_chat_client.post.called
        call_args = mock_chat_client.post.call_args
        assert f"/internal/chat/messages/{message_id}/transcription" in call_args[0][0]
        assert call_args[1]["json"]["transcribed_text"] == transcribed_text

    @pytest.mark.asyncio
    async def test_save_transcription_empty_text(self, settings: SalesAgentSettings) -> None:
        """Test transcription save with empty text."""
        settings.backend.url = "http://localhost:8001"
        client = BackendClient(settings)

        message_id = "msg-empty"
        transcribed_text = ""
        response_data = {
            "message_id": message_id,
            "thread_id": "thread-empty",
            "role": "user",
            "content": "",
            "transcription": None,
            "type": "audio",
            "artifact_ids": [],
            "created_at": "2025-01-01T00:00:00Z",
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = response_data
        mock_response.raise_for_status = MagicMock()

        mock_chat_client = AsyncMock()
        mock_chat_client.post = AsyncMock(return_value=mock_response)
        client._chat_client = mock_chat_client

        result = await client.save_transcription(message_id, transcribed_text)

        assert result["content"] == ""
        assert result.get("transcription") is None

    @pytest.mark.asyncio
    async def test_save_transcription_message_not_found(self, settings: SalesAgentSettings) -> None:
        """Test transcription save when message doesn't exist."""
        settings.backend.url = "http://localhost:8001"
        client = BackendClient(settings)

        message_id = "nonexistent-msg-id"
        transcribed_text = "Some text"

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Not found", request=MagicMock(), response=mock_response
        )

        mock_chat_client = AsyncMock()
        mock_chat_client.post = AsyncMock(return_value=mock_response)
        client._chat_client = mock_chat_client

        with pytest.raises(httpx.HTTPStatusError):
            await client.save_transcription(message_id, transcribed_text)

    @pytest.mark.asyncio
    async def test_save_transcription_http_error(self, settings: SalesAgentSettings) -> None:
        """Test transcription save when HTTP request fails."""
        settings.backend.url = "http://localhost:8001"
        client = BackendClient(settings)

        message_id = "msg-error"
        transcribed_text = "Some text"

        mock_chat_client = AsyncMock()
        mock_chat_client.post = AsyncMock(side_effect=httpx.HTTPError("Connection error"))
        client._chat_client = mock_chat_client

        with pytest.raises(httpx.HTTPError):
            await client.save_transcription(message_id, transcribed_text)

    @pytest.mark.asyncio
    async def test_save_transcription_overwrites_existing(self, settings: SalesAgentSettings) -> None:
        """Test transcription save returns updated transcription from API."""
        settings.backend.url = "http://localhost:8001"
        client = BackendClient(settings)

        message_id = "msg-overwrite"
        old_text = "Old transcription"
        new_text = "New transcription"
        response_data = {
            "message_id": message_id,
            "thread_id": "thread-overwrite",
            "role": "user",
            "content": "",
            "transcription": new_text,
            "type": "audio",
            "artifact_ids": ["company_1/voice/audio.mp3"],
            "created_at": "2025-01-01T00:00:00Z",
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = response_data
        mock_response.raise_for_status = MagicMock()

        mock_chat_client = AsyncMock()
        mock_chat_client.post = AsyncMock(return_value=mock_response)
        client._chat_client = mock_chat_client

        result = await client.save_transcription(message_id, new_text)

        assert result["transcription"] == new_text
        assert result["transcription"] != old_text
