"""Tests for chat message artifact and transcription endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.backend.modules.chat.models import (
    ChatMessage,
    ChatMessageRole,
    ChatMessageStatus,
    ChatMessageType,
    Customer,
    Thread,
)
from src.backend.modules.s3_storage.exceptions import S3FileNotFoundError, S3StorageError


@pytest.mark.asyncio
async def test_get_message_success(
    api_client: httpx.AsyncClient,
    service_headers: dict[str, str],
    company_factory,
):
    """Test successful message retrieval with artifact_ids."""
    company = await company_factory()
    customer = await Customer.create(
        user_id="user-123",
        company=company,
        quiz_answers={},
    )
    thread = await Thread.create(
        thread_id="thread-123",
        customer=customer,
        company=company,
        channel_type="telegram",
        conversation_id="conv-123",
    )

    message = await ChatMessage.create(
        message_id="msg-123",
        thread=thread,
        role=ChatMessageRole.USER,
        content="Hello",
        type=ChatMessageType.TEXT,
        status=ChatMessageStatus.DELIVERED,
        artifact_ids=["company_1/voice/test1.mp3", "company_1/image/test2.jpg"],
    )

    response = await api_client.get(
        f"/api/v1/internal/chat/messages/{message.message_id}",
        headers=service_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["message_id"] == message.message_id
    assert data["content"] == "Hello"
    assert data["artifact_ids"] == ["company_1/voice/test1.mp3", "company_1/image/test2.jpg"]
    assert data["type"] == ChatMessageType.TEXT.value


@pytest.mark.asyncio
async def test_get_message_with_transcription(
    api_client: httpx.AsyncClient,
    service_headers: dict[str, str],
    company_factory,
):
    """Test message retrieval with transcription on the message."""
    company = await company_factory()
    customer = await Customer.create(
        user_id="user-456",
        company=company,
        quiz_answers={},
    )
    thread = await Thread.create(
        thread_id="thread-456",
        customer=customer,
        company=company,
        channel_type="telegram",
        conversation_id="conv-456",
    )

    message = await ChatMessage.create(
        message_id="msg-456",
        thread=thread,
        role=ChatMessageRole.USER,
        content="",
        transcription="This is a transcribed text from audio",
        type=ChatMessageType.TEXT,
        status=ChatMessageStatus.DELIVERED,
        artifact_ids=["company_1/voice/audio123.mp3"],
    )

    response = await api_client.get(
        f"/api/v1/internal/chat/messages/{message.message_id}",
        headers=service_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["message_id"] == message.message_id
    assert data["content"] == ""
    assert data["transcription"] == "This is a transcribed text from audio"
    assert data["type"] == ChatMessageType.TEXT.value
    assert len(data["artifact_ids"]) == 1


@pytest.mark.asyncio
async def test_get_message_not_found(
    api_client: httpx.AsyncClient,
    service_headers: dict[str, str],
):
    """Test message retrieval when message doesn't exist."""
    response = await api_client.get(
        "/api/v1/internal/messages/nonexistent-msg-id",
        headers=service_headers,
    )

    assert response.status_code == 404
    data = response.json()
    assert "not found" in data["detail"].lower()


@pytest.mark.asyncio
async def test_get_message_missing_service_key(
    api_client: httpx.AsyncClient,
    company_factory,
):
    """Test message retrieval without service key."""
    company = await company_factory()
    customer = await Customer.create(
        user_id="user-789",
        company=company,
        quiz_answers={},
    )
    thread = await Thread.create(
        thread_id="thread-789",
        customer=customer,
        company=company,
        channel_type="telegram",
        conversation_id="conv-789",
    )

    message = await ChatMessage.create(
        message_id="msg-789",
        thread=thread,
        role=ChatMessageRole.USER,
        content="Hello",
        type=ChatMessageType.TEXT,
        status=ChatMessageStatus.DELIVERED,
    )

    response = await api_client.get(
        f"/api/v1/internal/chat/messages/{message.message_id}",
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_message_empty_artifact_ids(
    api_client: httpx.AsyncClient,
    service_headers: dict[str, str],
    company_factory,
):
    """Test message retrieval with empty artifact_ids list."""
    company = await company_factory()
    customer = await Customer.create(
        user_id="user-empty",
        company=company,
        quiz_answers={},
    )
    thread = await Thread.create(
        thread_id="thread-empty",
        customer=customer,
        company=company,
        channel_type="telegram",
        conversation_id="conv-empty",
    )

    message = await ChatMessage.create(
        message_id="msg-empty",
        thread=thread,
        role=ChatMessageRole.USER,
        content="Text message",
        type=ChatMessageType.TEXT,
        status=ChatMessageStatus.DELIVERED,
        artifact_ids=[],
    )

    response = await api_client.get(
        f"/api/v1/internal/chat/messages/{message.message_id}",
        headers=service_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["artifact_ids"] == []


@pytest.mark.asyncio
async def test_save_transcription_success(
    api_client: httpx.AsyncClient,
    service_headers: dict[str, str],
    company_factory,
):
    """Test successful transcription save."""
    company = await company_factory()
    customer = await Customer.create(
        user_id="user-trans",
        company=company,
        quiz_answers={},
    )
    thread = await Thread.create(
        thread_id="thread-trans",
        customer=customer,
        company=company,
        channel_type="telegram",
        conversation_id="conv-trans",
    )

    message = await ChatMessage.create(
        message_id="msg-trans",
        thread=thread,
        role=ChatMessageRole.USER,
        content="",
        type=ChatMessageType.TEXT,
        status=ChatMessageStatus.DELIVERED,
        artifact_ids=["company_1/voice/audio.mp3"],
    )

    transcribed_text = "This is the transcribed text from the audio file"

    response = await api_client.post(
        f"/api/v1/internal/chat/messages/{message.message_id}/transcription",
        json={"transcribed_text": transcribed_text},
        headers=service_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["content"] == ""
    assert data["transcription"] == transcribed_text
    assert data["message_id"] == message.message_id

    await message.refresh_from_db()
    assert message.content == ""
    assert message.transcription == transcribed_text


@pytest.mark.asyncio
async def test_save_transcription_manager(
    api_client: httpx.AsyncClient,
    service_headers: dict[str, str],
    company_factory,
):
    company = await company_factory()
    customer = await Customer.create(
        user_id="user-trans-mgr",
        company=company,
        quiz_answers={},
    )
    thread = await Thread.create(
        thread_id="thread-trans-mgr",
        customer=customer,
        company=company,
        channel_type="telegram",
        conversation_id="conv-trans-mgr",
    )

    message = await ChatMessage.create(
        message_id="msg-trans-mgr",
        thread=thread,
        role=ChatMessageRole.MANAGER,
        content="",
        type=ChatMessageType.TEXT,
        status=ChatMessageStatus.DELIVERED,
        artifact_ids=["company_1/voice/mgr.ogg"],
    )

    transcribed_text = "Manager said this on voice"

    response = await api_client.post(
        f"/api/v1/internal/chat/messages/{message.message_id}/transcription",
        json={"transcribed_text": transcribed_text},
        headers=service_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["content"] == ""
    assert data["transcription"] == transcribed_text

    await message.refresh_from_db()
    assert message.content == ""
    assert message.transcription == transcribed_text


@pytest.mark.asyncio
async def test_save_transcription_overwrites_existing(
    api_client: httpx.AsyncClient,
    service_headers: dict[str, str],
    company_factory,
):
    """Test transcription save updates transcription without changing content."""
    company = await company_factory()
    customer = await Customer.create(
        user_id="user-overwrite",
        company=company,
        quiz_answers={},
    )
    thread = await Thread.create(
        thread_id="thread-overwrite",
        customer=customer,
        company=company,
        channel_type="telegram",
        conversation_id="conv-overwrite",
    )

    message = await ChatMessage.create(
        message_id="msg-overwrite",
        thread=thread,
        role=ChatMessageRole.USER,
        content="User caption unchanged",
        transcription="Old transcription",
        type=ChatMessageType.TEXT,
        status=ChatMessageStatus.DELIVERED,
        artifact_ids=["company_1/voice/audio.mp3"],
    )

    new_transcription = "New transcription text"

    response = await api_client.post(
        f"/api/v1/internal/chat/messages/{message.message_id}/transcription",
        json={"transcribed_text": new_transcription},
        headers=service_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["content"] == "User caption unchanged"
    assert data["transcription"] == new_transcription

    await message.refresh_from_db()
    assert message.content == "User caption unchanged"
    assert message.transcription == new_transcription


@pytest.mark.asyncio
async def test_save_transcription_empty_text(
    api_client: httpx.AsyncClient,
    service_headers: dict[str, str],
    company_factory,
):
    """Test transcription save with empty text."""
    company = await company_factory()
    customer = await Customer.create(
        user_id="user-empty-trans",
        company=company,
        quiz_answers={},
    )
    thread = await Thread.create(
        thread_id="thread-empty-trans",
        customer=customer,
        company=company,
        channel_type="telegram",
        conversation_id="conv-empty-trans",
    )

    message = await ChatMessage.create(
        message_id="msg-empty-trans",
        thread=thread,
        role=ChatMessageRole.USER,
        content="",
        type=ChatMessageType.TEXT,
        status=ChatMessageStatus.DELIVERED,
        artifact_ids=["company_1/voice/audio.mp3"],
    )

    response = await api_client.post(
        f"/api/v1/internal/chat/messages/{message.message_id}/transcription",
        json={"transcribed_text": ""},
        headers=service_headers,
    )

    assert response.status_code == 400
    assert "transcribed_text is required" in response.json()["detail"]


@pytest.mark.asyncio
async def test_save_transcription_message_not_found(
    api_client: httpx.AsyncClient,
    service_headers: dict[str, str],
):
    """Test transcription save when message doesn't exist."""
    response = await api_client.post(
        "/api/v1/internal/messages/nonexistent-msg-id/transcription",
        json={"transcribed_text": "Some text"},
        headers=service_headers,
    )

    assert response.status_code == 404
    data = response.json()
    assert "not found" in data["detail"].lower()


@pytest.mark.asyncio
async def test_save_transcription_missing_service_key(
    api_client: httpx.AsyncClient,
    company_factory,
):
    """Test transcription save without service key."""
    company = await company_factory()
    customer = await Customer.create(
        user_id="user-no-auth",
        company=company,
        quiz_answers={},
    )
    thread = await Thread.create(
        thread_id="thread-no-auth",
        customer=customer,
        company=company,
        channel_type="telegram",
        conversation_id="conv-no-auth",
    )

    message = await ChatMessage.create(
        message_id="msg-no-auth",
        thread=thread,
        role=ChatMessageRole.USER,
        content="",
        type=ChatMessageType.TEXT,
        status=ChatMessageStatus.DELIVERED,
    )

    response = await api_client.post(
        f"/api/v1/internal/chat/messages/{message.message_id}/transcription",
        json={"transcribed_text": "Some text"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_save_transcription_missing_field(
    api_client: httpx.AsyncClient,
    service_headers: dict[str, str],
    company_factory,
):
    """Test transcription save with missing transcribed_text field."""
    company = await company_factory()
    customer = await Customer.create(
        user_id="user-missing-field",
        company=company,
        quiz_answers={},
    )
    thread = await Thread.create(
        thread_id="thread-missing-field",
        customer=customer,
        company=company,
        channel_type="telegram",
        conversation_id="conv-missing-field",
    )

    message = await ChatMessage.create(
        message_id="msg-missing-field",
        thread=thread,
        role=ChatMessageRole.USER,
        content="",
        type=ChatMessageType.TEXT,
        status=ChatMessageStatus.DELIVERED,
    )

    response = await api_client.post(
        f"/api/v1/internal/chat/messages/{message.message_id}/transcription",
        json={},
        headers=service_headers,
    )

    assert response.status_code == 400
    assert "transcribed_text is required" in response.json()["detail"]


@pytest.mark.asyncio
async def test_download_artifact_success(
    company_factory,
):
    """Test successful artifact download from message."""
    company = await company_factory()
    customer = await Customer.create(
        user_id="user-download",
        company=company,
        quiz_answers={},
    )
    thread = await Thread.create(
        thread_id="thread-download",
        customer=customer,
        company=company,
        channel_type="telegram",
        conversation_id="conv-download",
    )

    artifact_id = f"company_{company.id}/voice/test.mp3"
    message = await ChatMessage.create(
        message_id="msg-download",
        thread=thread,
        role=ChatMessageRole.USER,
        content="",
        type=ChatMessageType.TEXT,
        status=ChatMessageStatus.DELIVERED,
        artifact_ids=[artifact_id],
    )

    file_bytes = b"fake audio content"

    with patch("src.backend.modules.chat.models.S3Client") as mock_s3_class:
        mock_s3 = AsyncMock()
        mock_s3.download_file = AsyncMock(return_value=file_bytes)
        mock_s3_class.return_value = mock_s3

        results = await message.download_artifacts(mock_s3)

        assert len(results) == 1
        assert results[0] == file_bytes
        assert mock_s3.download_file.called
        assert mock_s3.download_file.call_args[0][0] == artifact_id


@pytest.mark.asyncio
async def test_download_artifact_empty_list(
    company_factory,
):
    """Test artifact download when message has no artifacts."""
    company = await company_factory()
    customer = await Customer.create(
        user_id="user-no-artifacts",
        company=company,
        quiz_answers={},
    )
    thread = await Thread.create(
        thread_id="thread-no-artifacts",
        customer=customer,
        company=company,
        channel_type="telegram",
        conversation_id="conv-no-artifacts",
    )

    message = await ChatMessage.create(
        message_id="msg-no-artifacts",
        thread=thread,
        role=ChatMessageRole.USER,
        content="",
        type=ChatMessageType.TEXT,
        status=ChatMessageStatus.DELIVERED,
        artifact_ids=[],
    )

    with patch("src.backend.modules.chat.models.S3Client") as mock_s3_class:
        mock_s3 = AsyncMock()
        mock_s3_class.return_value = mock_s3

        results = await message.download_artifacts(mock_s3)

        assert results == []
        assert not mock_s3.download_file.called


@pytest.mark.asyncio
async def test_download_artifact_not_found(
    company_factory,
):
    """Test artifact download when file doesn't exist in S3."""
    company = await company_factory()
    customer = await Customer.create(
        user_id="user-not-found",
        company=company,
        quiz_answers={},
    )
    thread = await Thread.create(
        thread_id="thread-not-found",
        customer=customer,
        company=company,
        channel_type="telegram",
        conversation_id="conv-not-found",
    )

    artifact_id = f"company_{company.id}/voice/nonexistent.mp3"
    message = await ChatMessage.create(
        message_id="msg-not-found",
        thread=thread,
        role=ChatMessageRole.USER,
        content="",
        type=ChatMessageType.TEXT,
        status=ChatMessageStatus.DELIVERED,
        artifact_ids=[artifact_id],
    )

    with patch("src.backend.modules.chat.models.S3Client") as mock_s3_class:
        mock_s3 = AsyncMock()
        mock_s3.download_file = AsyncMock(side_effect=S3FileNotFoundError("File not found"))
        mock_s3_class.return_value = mock_s3

        with pytest.raises(S3FileNotFoundError):
            await message.download_artifacts(mock_s3)


@pytest.mark.asyncio
async def test_download_artifact_s3_error(
    company_factory,
):
    """Test artifact download when S3 operation fails."""
    company = await company_factory()
    customer = await Customer.create(
        user_id="user-s3-error",
        company=company,
        quiz_answers={},
    )
    thread = await Thread.create(
        thread_id="thread-s3-error",
        customer=customer,
        company=company,
        channel_type="telegram",
        conversation_id="conv-s3-error",
    )

    artifact_id = f"company_{company.id}/voice/test.mp3"
    message = await ChatMessage.create(
        message_id="msg-s3-error",
        thread=thread,
        role=ChatMessageRole.USER,
        content="",
        type=ChatMessageType.TEXT,
        status=ChatMessageStatus.DELIVERED,
        artifact_ids=[artifact_id],
    )

    with patch("src.backend.modules.chat.models.S3Client") as mock_s3_class:
        mock_s3 = AsyncMock()
        mock_s3.download_file = AsyncMock(side_effect=S3StorageError("S3 error"))
        mock_s3_class.return_value = mock_s3

        with pytest.raises(S3StorageError):
            await message.download_artifacts(mock_s3)


@pytest.mark.asyncio
async def test_download_artifact_multiple_artifacts(
    company_factory,
):
    """Test artifact download when message has multiple artifacts."""
    company = await company_factory()
    customer = await Customer.create(
        user_id="user-multiple",
        company=company,
        quiz_answers={},
    )
    thread = await Thread.create(
        thread_id="thread-multiple",
        customer=customer,
        company=company,
        channel_type="telegram",
        conversation_id="conv-multiple",
    )

    artifact_id_1 = f"company_{company.id}/voice/audio1.mp3"
    artifact_id_2 = f"company_{company.id}/image/image1.jpg"
    message = await ChatMessage.create(
        message_id="msg-multiple",
        thread=thread,
        role=ChatMessageRole.USER,
        content="",
        type=ChatMessageType.TEXT,
        status=ChatMessageStatus.DELIVERED,
        artifact_ids=[artifact_id_1, artifact_id_2],
    )

    file_bytes_1 = b"audio content"
    file_bytes_2 = b"image content"

    with patch("src.backend.modules.chat.models.S3Client") as mock_s3_class:
        mock_s3 = AsyncMock()
        mock_s3.download_file = AsyncMock(side_effect=[file_bytes_1, file_bytes_2])
        mock_s3_class.return_value = mock_s3

        results = await message.download_artifacts(mock_s3)

        assert len(results) == 2
        assert results[0] == file_bytes_1
        assert results[1] == file_bytes_2
        assert mock_s3.download_file.call_count == 2
        assert mock_s3.download_file.call_args_list[0][0][0] == artifact_id_1
        assert mock_s3.download_file.call_args_list[1][0][0] == artifact_id_2
