from __future__ import annotations

import pytest
from pydantic import SecretStr

from common.config import (
    ConnectorDebounceSettings,
    ConnectorSecretSettings,
    ConnectorSettings,
)

from src.sales_agent.connectors.base import (
    ConnectorAuthError,
    ConnectorPayloadError,
    InboundPayload,
)
from src.sales_agent.connectors.wappi_hub import WappiHubInboundConnector


@pytest.mark.asyncio
async def test_wappi_hub_inbound_normalizes_minimal_payload() -> None:
    settings = ConnectorSettings(
        connector_id="wappi-test",
        type="messaging",
        channel_types=["telegram"],
        debounce=ConnectorDebounceSettings(window_seconds=30),
        secrets=ConnectorSecretSettings(extra={"webhook_secret": SecretStr("secret-token")}),
        metadata={"provider": "wappi-hub"},
    )
    connector = WappiHubInboundConnector(settings, default_window=45)

    payload = InboundPayload(
        body={
            "messages": [
                {
                    "id": "5902",
                    "profile_id": "51a8107a-5442",
                    "wh_type": "incoming_message",
                    "timestamp": "2025-03-17T15:14:37+03:00",
                    "time": 1742213677,
                    "body": "hello",
                    "type": "text",
                    "from": "60227586",
                    "to": "5279188641",
                    "senderName": "Test User",
                    "chatId": "conv-1",
                    "from_where": "phone",
                    "username": "testuser",
                    "chat_type": "user",
                }
            ]
        },
        headers={"X-Wappi-Signature": "secret-token", "X-Company-Id": "42"},
    )

    messages = await connector.normalize(payload)
    assert len(messages) == 1

    msg = messages[0]
    assert msg.connector_id == "wappi-test"
    assert msg.conversation_id == "conv-1"
    # AICODE-NOTE: user_id is now conversation_id (chat_id), not username
    # Username is stored in metadata for customer meta field
    assert msg.user_id == "conv-1"
    assert msg.text == "hello"
    assert msg.metadata["provider_id"] == "51a8107a-5442"
    assert msg.metadata["channel_type"] == "telegram"
    assert msg.metadata["company_id"] == "42"
    assert msg.metadata["chat_id"] == "conv-1"
    # Username should be in metadata for customer meta
    assert msg.metadata.get("username") == "testuser"


@pytest.mark.asyncio
async def test_wappi_hub_inbound_auth_failure_raises() -> None:
    settings = ConnectorSettings(
        connector_id="wappi-test",
        type="messaging",
        channel_types=["telegram"],
        debounce=ConnectorDebounceSettings(window_seconds=30),
        secrets=ConnectorSecretSettings(extra={"webhook_secret": SecretStr("secret-token")}),
        metadata={"provider": "wappi-hub"},
    )
    connector = WappiHubInboundConnector(settings, default_window=45)

    payload = InboundPayload(
        body={
            "messages": [
                {
                    "id": "5902",
                    "profile_id": "51a8107a-5442",
                    "body": "hello",
                    "type": "text",
                    "chatId": "conv-1",
                    "from_where": "phone",
                }
            ]
        },
        headers={"X-Wappi-Signature": "wrong-token"},
    )

    with pytest.raises(ConnectorAuthError):
        await connector.normalize(payload)


@pytest.mark.asyncio
async def test_wappi_hub_inbound_missing_messages_raises() -> None:
    settings = ConnectorSettings(
        connector_id="wappi-test",
        type="messaging",
        channel_types=["telegram"],
        debounce=ConnectorDebounceSettings(window_seconds=30),
        secrets=ConnectorSecretSettings(),
        metadata={"provider": "wappi-hub"},
    )
    connector = WappiHubInboundConnector(settings, default_window=45)

    payload = InboundPayload(
        body={},
        headers={},
    )

    with pytest.raises(ConnectorPayloadError):
        await connector.normalize(payload)


@pytest.mark.asyncio
async def test_wappi_hub_inbound_telegram_voice_ptt() -> None:
    settings = ConnectorSettings(
        connector_id="wappi-test",
        type="messaging",
        channel_types=["telegram"],
        debounce=ConnectorDebounceSettings(window_seconds=30),
        secrets=ConnectorSecretSettings(),
        metadata={"provider": "wappi-hub"},
    )
    connector = WappiHubInboundConnector(settings, default_window=45)

    payload = InboundPayload(
        body={
            "messages": [
                {
                    "id": "5908",
                    "profile_id": "51a8107a-5442",
                    "wh_type": "incoming_message",
                    "time": 1742214119,
                    "body": "dGVzdF9hdWRpb19kYXRh",  # pragma: allowlist secret
                    "type": "ptt",
                    "chatId": "60227586",
                    "from_where": "phone",
                    "mimetype": "audio/ogg",
                    "username": "sinay",
                    "senderName": "Sinn",
                    "chat_type": "user",
                    "length_seconds": 1,
                }
            ]
        },
        headers={},
    )

    messages = await connector.normalize(payload)
    assert len(messages) == 1

    msg = messages[0]
    assert msg.text is None
    assert len(msg.attachments) == 1
    assert msg.attachments[0]["type"] == "audio"
    assert msg.attachments[0]["bytes_base64"] == "dGVzdF9hdWRpb19kYXRh"
    assert msg.attachments[0]["mime"] == "audio/ogg"
    assert msg.attachments[0]["duration_s"] == 1.0
    assert "voice_5908" in msg.attachments[0]["filename"]


@pytest.mark.asyncio
async def test_wappi_hub_inbound_telegram_rejects_non_text_non_ptt() -> None:
    settings = ConnectorSettings(
        connector_id="wappi-test",
        type="messaging",
        channel_types=["telegram"],
        debounce=ConnectorDebounceSettings(window_seconds=30),
        secrets=ConnectorSecretSettings(),
        metadata={"provider": "wappi-hub"},
    )
    connector = WappiHubInboundConnector(settings, default_window=45)

    payload = InboundPayload(
        body={
            "messages": [
                {
                    "id": "5909",
                    "profile_id": "51a8107a-5442",
                    "type": "photo",
                    "chatId": "60227586",
                    "from_where": "phone",
                    "username": "testuser",
                }
            ]
        },
        headers={},
    )

    messages = await connector.normalize(payload)
    assert len(messages) == 0


@pytest.mark.asyncio
async def test_wappi_hub_inbound_channel_metadata_included() -> None:
    settings = ConnectorSettings(
        connector_id="wappi-test",
        type="messaging",
        channel_types=["telegram"],
        debounce=ConnectorDebounceSettings(window_seconds=30),
        secrets=ConnectorSecretSettings(),
        metadata={"provider": "wappi-hub"},
    )
    connector = WappiHubInboundConnector(settings, default_window=45)

    payload = InboundPayload(
        body={
            "messages": [
                {
                    "id": "5902",
                    "profile_id": "51a8107a-5442",
                    "body": "reply message",
                    "type": "text",
                    "chatId": "conv-1",
                    "from_where": "phone",
                    "username": "testuser",
                    "senderName": "Test User",
                    "chat_type": "user",
                    "is_forwarded": True,
                }
            ]
        },
        headers={},
    )

    messages = await connector.normalize(payload)
    msg = messages[0]
    assert msg.metadata["message_id"] == "5902"
    assert msg.metadata["sender_name"] == "Test User"
    assert msg.metadata["username"] == "testuser"
    assert msg.metadata["is_forwarded"] is True


@pytest.mark.asyncio
async def test_wappi_hub_inbound_whatsapp_text_message() -> None:
    settings = ConnectorSettings(
        connector_id="wappi-test",
        type="messaging",
        channel_types=["whatsapp"],
        debounce=ConnectorDebounceSettings(window_seconds=30),
        secrets=ConnectorSecretSettings(),
        metadata={"provider": "wappi-hub"},
    )
    connector = WappiHubInboundConnector(settings, default_window=45)

    payload = InboundPayload(
        body={
            "messages": [
                {
                    "wh_type": "incoming_message",
                    "profile_id": "6qw54f68-71eq",
                    "id": "msg_test_001",  # pragma: allowlist secret
                    "body": "Ответ на сообщение",
                    "type": "chat",
                    "from": "79115576366@c.us",
                    "to": "79602041988@c.us",
                    "senderName": "Flood",
                    "chatId": "79115576366@c.us",
                    "time": 1729499277,
                    "from_where": "phone",
                    "contact_name": "Максим",
                    "isReply": True,
                    "chat_type": "dialog",
                    "reply_message": {
                        "id": "reply_test_001",  # pragma: allowlist secret
                        "body": "Previous message",
                        "type": "text",
                    },
                }
            ]
        },
        headers={},
    )

    messages = await connector.normalize(payload)
    assert len(messages) == 1

    msg = messages[0]
    assert msg.text == "Ответ на сообщение"
    assert msg.conversation_id == "79115576366@c.us"
    assert msg.user_id == "79115576366@c.us"
    assert msg.metadata["channel_type"] == "whatsapp"
    assert msg.metadata["message_id"] == "msg_test_001"
    assert msg.metadata["sender_name"] == "Flood"
    assert msg.metadata["contact_name"] == "Максим"
    assert msg.metadata["from"] == "79115576366@c.us"
    assert msg.metadata["is_reply"] is True
    assert msg.metadata["reply_to_message_id"] == "reply_test_001"


@pytest.mark.asyncio
async def test_wappi_hub_inbound_whatsapp_voice_ptt() -> None:
    settings = ConnectorSettings(
        connector_id="wappi-test",
        type="messaging",
        channel_types=["whatsapp"],
        debounce=ConnectorDebounceSettings(window_seconds=30),
        secrets=ConnectorSecretSettings(),
        metadata={"provider": "wappi-hub"},
    )
    connector = WappiHubInboundConnector(settings, default_window=45)

    payload = InboundPayload(
        body={
            "messages": [
                {
                    "wh_type": "incoming_message",
                    "profile_id": "71ad40e9-b023",
                    "id": "voice_test_001",  # pragma: allowlist secret
                    "body": "dGVzdF9hdWRpb19kYXRh",  # pragma: allowlist secret
                    "type": "ptt",
                    "from": "79005576333@c.us",
                    "to": "79662041999@c.us",
                    "senderName": "Flood",
                    "chatId": "79005576333@c.us",
                    "time": 1701770821,
                    "from_where": "phone",
                    "mimetype": "audio/ogg; codecs=opus",
                    "contact_name": "Максим",
                    "chat_type": "dialog",
                }
            ]
        },
        headers={},
    )

    messages = await connector.normalize(payload)
    assert len(messages) == 1

    msg = messages[0]
    assert msg.text is None
    assert len(msg.attachments) == 1
    assert msg.attachments[0]["type"] == "audio"
    assert msg.attachments[0]["bytes_base64"] == "dGVzdF9hdWRpb19kYXRh"
    assert msg.attachments[0]["mime"] == "audio/ogg; codecs=opus"
    assert "voice_voice_test_001" in msg.attachments[0]["filename"]
    assert msg.conversation_id == "79005576333@c.us"
    assert msg.user_id == "79005576333@c.us"
    assert msg.metadata["channel_type"] == "whatsapp"


@pytest.mark.asyncio
async def test_wappi_hub_inbound_whatsapp_rejects_non_chat_non_ptt() -> None:
    settings = ConnectorSettings(
        connector_id="wappi-test",
        type="messaging",
        channel_types=["whatsapp"],
        debounce=ConnectorDebounceSettings(window_seconds=30),
        secrets=ConnectorSecretSettings(),
        metadata={"provider": "wappi-hub"},
    )
    connector = WappiHubInboundConnector(settings, default_window=45)

    payload = InboundPayload(
        body={
            "messages": [
                {
                    "id": "img_test_001",  # pragma: allowlist secret
                    "profile_id": "6qw54f68-71eq",
                    "type": "image",
                    "from": "79115576366@c.us",
                    "chatId": "79115576366@c.us",
                }
            ]
        },
        headers={},
    )

    messages = await connector.normalize(payload)
    assert len(messages) == 0
