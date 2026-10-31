"""Base sync provider interface for connector modules."""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any

from common.contracts.sync import SyncMessage


class Dialog:
    """Dialog/conversation from external API."""

    def __init__(self, id: str, name: str | None = None, metadata: dict[str, Any] | None = None):
        self.id = id
        self.name = name
        self.metadata = metadata or {}


RawMessage = dict[str, Any]


class BaseSyncProvider(ABC):
    """Abstract base class for sync providers.

    Connector modules implement this interface to provide provider-specific
    sync logic. The framework handles orchestration, batching, retries, etc.
    """

    @abstractmethod
    def fetch_dialogs(self, cursor: str | None = None, max_dialogs: int | None = None) -> AsyncIterator[Dialog]:
        """Fetch list of dialogs from external API.

        Args:
            cursor: Optional cursor for pagination/resume
            max_dialogs: Optional maximum number of dialogs to fetch (for initial sync)

        Yields:
            Dialog objects from external API
        """
        ...

    @abstractmethod
    def fetch_messages(
        self,
        dialog_id: str,
        cursor: str | None = None,
        since: str | None = None,
        max_messages: int | None = None,
    ) -> AsyncIterator[RawMessage]:
        """Fetch messages from a dialog.

        Args:
            dialog_id: Dialog identifier
            cursor: Optional cursor for pagination/resume
            since: Optional date string for catchup sync (format: YYYY-mm-ddTHH:MM:ss)
            max_messages: Optional maximum number of messages to fetch (for initial sync)

        Yields:
            Raw message dictionaries from external API
        """
        ...

    @abstractmethod
    async def transform_message(self, raw: RawMessage) -> SyncMessage:
        """Transform provider-specific message format to SyncMessage.

        Args:
            raw: Raw message dictionary from external API

        Returns:
            Normalized SyncMessage

        Note:
            Async to support media processing (download, convert, upload to S3)
        """
        ...

    @abstractmethod
    def get_rate_limit(self) -> float:
        """Get rate limit for this provider (requests per second).

        Returns:
            Rate limit as float (e.g., 2.0 for 2 req/sec)
        """
        ...

    @abstractmethod
    def get_initial_sync_limit(self) -> int | None:
        """Get message limit for initial sync per dialog.

        Returns:
            Maximum number of messages to sync per dialog during initial sync, or None for no limit
        """
        ...

    @abstractmethod
    def get_initial_dialogs_limit(self) -> int | None:
        """Get dialog limit for initial sync.

        Returns:
            Maximum number of dialogs to sync during initial sync, or None for no limit
        """
        ...
