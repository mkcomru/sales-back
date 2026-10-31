from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class UserInput:
    user_id: int
    text: str
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class SimpleUser:
    id: int


@dataclass
class SimpleChat:
    id: int


@dataclass
class SimpleMessage:
    """
    The minimum object compatible with aiogram Message,
    sufficient for the existing process_user_message(message, settings).
    """

    text: str
    from_user: SimpleUser
    chat: SimpleChat
    message_id: int
    metadata: dict[str, Any] = field(default_factory=dict)
