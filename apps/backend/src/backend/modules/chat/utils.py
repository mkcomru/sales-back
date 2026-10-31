"""Utility functions for chat module."""

from src.backend.modules.chat.models import ChatMessage
from src.backend.modules.chat.schemas import AuthorInfo


def get_author_info(message: ChatMessage) -> AuthorInfo | None:
    """Extract full author information from message's author relation.

    Args:
        message: ChatMessage instance with author__user relation prefetched via fetch_related()

    Returns:
        AuthorInfo if message has author, None if no author

    Raises:
        AttributeError: If author__user relation is not loaded (call fetch_related first)
        ValueError: If author exists but user relation is missing
    """
    try:
        author = message.author
    except AttributeError:
        raise AttributeError(
            f"Message {message.message_id} author relation not loaded. "
            "Call fetch_related('author__user') or prefetch_related('author__user') first"
        ) from None

    if author is None:
        return None

    try:
        user = author.user
    except AttributeError:
        raise AttributeError(
            f"CompanyUser {author.id} user relation not loaded. "
            "Call fetch_related('author__user') or prefetch_related('author__user') first"
        ) from None

    if user is None:
        raise ValueError(f"CompanyUser {author.id} has no user relation. This indicates a data integrity issue.")

    return AuthorInfo(
        id=author.id,
        user_id=user.id,
        first_name=user.first_name,
        last_name=user.last_name,
        email=user.email,
        role=author.role.value,
    )
