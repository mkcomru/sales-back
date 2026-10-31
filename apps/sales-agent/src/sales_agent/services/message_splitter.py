from __future__ import annotations

import structlog

log = structlog.get_logger(__name__)

CHARS_PER_SECOND = 30
MIN_DELAY_SECONDS = 0.5


def remove_trailing_dots(text: str) -> str:
    """Remove trailing dots, keep only ! or ? if present.

    Args:
        text: Text to process

    Returns:
        Text with trailing dots removed (except ellipsis)
    """
    if not text:
        return text

    text = text.rstrip()

    if text.endswith("..."):
        return text

    if text.endswith("."):
        return text[:-1]

    return text


def split_message(text: str) -> list[str]:
    """Split message by double newlines (\n\n).

    Args:
        text: Message text to split

    Returns:
        List of message chunks (non-empty, stripped)
    """
    if not text or not text.strip():
        return []

    chunks = [chunk.strip() for chunk in text.split("\n\n") if chunk.strip()]
    return chunks if chunks else [text.strip()]


def calculate_delay(chunk: str) -> float:
    """Calculate delay in seconds based on chunk length.

    Args:
        chunk: Message chunk text

    Returns:
        Delay in seconds (max of MIN_DELAY_SECONDS and len(chunk) / CHARS_PER_SECOND)
    """
    delay = len(chunk) / CHARS_PER_SECOND
    return max(MIN_DELAY_SECONDS, delay)


def split_and_calculate_delays(text: str) -> tuple[list[str], list[float]]:
    """Split message and calculate delays for each chunk.

    Args:
        text: Message text to split

    Returns:
        Tuple of (chunks list, delays list in seconds)
    """
    processed_chunks = split_message(text)
    delays = [calculate_delay(chunk) for chunk in processed_chunks]

    log.debug(
        "message_splitter.split",
        chunks_count=len(processed_chunks),
        total_length=len(text),
        delays=delays,
    )

    return processed_chunks, delays
