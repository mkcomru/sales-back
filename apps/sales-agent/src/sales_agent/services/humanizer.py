from __future__ import annotations

import random
import re
from typing import Any

import structlog

from common import SalesAgentSettings as Settings

log = structlog.get_logger()


class MessageHumanizer:
    """Humanize bot messages by making them more natural and less robotic.

    Features:
    - Remove trailing dots (except ellipsis)
    - Replace emojis with parentheses based on recent history
    - Add natural variance to emotional markers
    - Maintain conversational flow
    """

    EMOJI_PATTERN = re.compile(
        r"[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF\u2600-\u26FF\u2700-\u27BF]+"  # noqa: E501
    )

    # Common emojis and their bracket equivalents
    EMOJI_TO_BRACKETS = {
        "😊": ")",
        "😉": ")",
        "👍": ")",
        "🙂": ")",
        "😄": "))",
        "😃": "))",
        "🤗": "))",
        "❤️": "))",
        "💪": ")",
        "✨": "",
        "🎉": ")",
    }

    def __init__(self):
        self._emoji_cooldown_messages = 3  # минимум сообщений между смайликами
        self._bracket_probability = 0.7  # вероятность замены эмодзи на скобки
        self._double_bracket_probability = 0.2  # вероятность двойных скобок

    def humanize(
        self,
        message: str,
        recent_bot_messages: list[str] | None = None,
    ) -> str:
        """Humanize a bot message based on conversation context.

        Args:
            message: The message to humanize
            recent_bot_messages: Recent bot messages (oldest first) for context

        Returns:
            Humanized message text
        """
        if not message or not message.strip():
            return message

        recent = recent_bot_messages or []

        # Process emojis based on recent history
        message = self._process_emojis(message, recent)

        # Add brackets if needed and no emojis present
        message = self._maybe_add_brackets(message, recent)

        log.debug(
            "humanizer.transform",
            original=message[:100],
            humanized=message[:100],
            recent_count=len(recent),
        )

        return message

    def _process_emojis(self, text: str, recent_messages: list[str]) -> str:
        """Replace emojis with brackets based on recent history."""
        # Count emojis in recent messages
        recent_emoji_count = self._count_recent_emojis(recent_messages)

        # If we had emojis recently, replace with brackets
        if recent_emoji_count >= 1:
            return self._replace_emojis_with_brackets(text)

        # Otherwise, keep emojis with some probability
        if random.random() < self._bracket_probability:
            return self._replace_emojis_with_brackets(text)

        # Keep emojis
        return text

    def _count_recent_emojis(self, messages: list[str]) -> int:
        """Count emojis in recent messages (last N messages)."""
        if not messages:
            return 0

        # Check last few messages
        check_count = min(self._emoji_cooldown_messages, len(messages))
        recent = messages[-check_count:]

        count = 0
        for msg in recent:
            if self.EMOJI_PATTERN.search(msg):
                count += 1

        return count

    def _replace_emojis_with_brackets(self, text: str) -> str:
        """Replace emojis with bracket smiles."""
        result = text

        # First, try known emoji mappings
        for emoji, brackets in self.EMOJI_TO_BRACKETS.items():
            if emoji in result:
                # Decide on single or double brackets
                if brackets == "))" or (brackets == ")" and random.random() < self._double_bracket_probability):
                    replacement = "))"
                else:
                    replacement = brackets if brackets else ""

                result = result.replace(emoji, replacement)

        # Then remove any remaining emojis
        result = self.EMOJI_PATTERN.sub("", result)

        return result.strip()

    def _maybe_add_brackets(self, text: str, recent_messages: list[str]) -> str:
        """Add brackets if message lacks emotional markers."""
        # Don't add if already has emojis or brackets
        if self.EMOJI_PATTERN.search(text):
            return text

        if ")" in text or "(" in text:
            return text

        # Check if recent messages have emotional markers
        recent_has_markers = any(self.EMOJI_PATTERN.search(msg) or ")" in msg for msg in recent_messages[-3:])

        # If recent messages had markers, occasionally skip adding
        if recent_has_markers and random.random() < 0.5:
            return text

        # Add brackets with some probability
        if random.random() < 0.3:
            # Decide single or double
            if random.random() < self._double_bracket_probability:
                return text + " ))"
            else:
                return text + " )"

        return text


# Global instance
_humanizer_instance: MessageHumanizer | None = None


def get_humanizer() -> MessageHumanizer:
    """Get global humanizer instance."""
    global _humanizer_instance
    if _humanizer_instance is None:
        _humanizer_instance = MessageHumanizer()
    return _humanizer_instance


async def humanize_message(
    message: str,
    *,
    history: list[dict[str, Any]] | None = None,
    settings: Settings | None = None,
) -> str:
    """Humanize a bot message using conversation history from envelope.

    Args:
        message: The message to humanize
        history: Recent messages from envelope [{role, content}, ...]
        settings: Optional settings for feature flag check

    Returns:
        Humanized message
    """
    _settings = settings if settings is not None else Settings()
    if not _settings.humanizer.enabled:
        return message

    recent_bot_messages = [msg["content"] for msg in (history or []) if msg.get("role") == "assistant"]

    humanizer = get_humanizer()
    return humanizer.humanize(message, recent_bot_messages)
