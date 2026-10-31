"""Sync framework for connector modules.

Shared infrastructure for history synchronization to avoid code duplication
across connector modules.
"""

from common.sync.base import BaseSyncProvider, Dialog, RawMessage
from common.sync.client import BackendSyncClient, BackendSyncClientError
from common.sync.rate_limiter import RateLimiter
from common.sync.runner import SyncRunner

__all__ = [
    "BaseSyncProvider",
    "Dialog",
    "RawMessage",
    "BackendSyncClient",
    "BackendSyncClientError",
    "RateLimiter",
    "SyncRunner",
]
