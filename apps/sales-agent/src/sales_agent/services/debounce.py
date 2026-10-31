import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import structlog

log = structlog.get_logger()
DEBOUNCE_SECONDS_DEFAULT = 45


@dataclass
class IncomingMessage:
    connector_id: str | None
    conversation_id: str
    user_id: str
    text: str | None = None
    attachments: list[dict[str, Any]] = field(default_factory=list)
    ts: float = field(default_factory=lambda: time.time())
    metadata: dict[str, Any] = field(default_factory=dict)
    debounce_seconds: int | None = None
    storage_key: str | None = None


class DebounceBucket:
    def __init__(self, storage_key: str, debounce_seconds: int):
        self.storage_key = storage_key
        self.debounce_seconds = debounce_seconds
        self.messages: list[IncomingMessage] = []
        self.lock = asyncio.Lock()
        self.task: asyncio.Task | None = None


class DebounceManager:
    """
    Transport-agnostic in-memory debouncer.
    Collects messages in a silent window and calls on_batch_callback once.
    Supports cancel_bucket_for_thread for early cancellation when assistant is deactivated.
    """

    def __init__(
        self,
        on_batch_callback: Callable[[str, list[IncomingMessage]], Awaitable[None]],
        debounce_seconds: int = DEBOUNCE_SECONDS_DEFAULT,
    ):
        self._on_batch_callback = on_batch_callback
        self._debounce_seconds = debounce_seconds
        self._buckets: dict[str, DebounceBucket] = {}
        self._thread_to_storage_key: dict[str, str] = {}
        self._global_lock = asyncio.Lock()

    @property
    def debounce_seconds(self) -> int:
        return self._debounce_seconds

    async def add_message(self, msg: IncomingMessage) -> int:
        # AICODE-NOTE: Two-level locking strategy for debounce buckets
        # 1. Global lock: protects bucket creation/lookup (short duration)
        # 2. Bucket lock: protects message list and timer task (per-conversation)
        # This avoids holding global lock during timer operations.
        storage_key = (msg.storage_key or msg.conversation_id).strip()
        if not storage_key:
            raise ValueError("IncomingMessage requires non-empty storage key")

        debounce_seconds = msg.debounce_seconds or self._debounce_seconds

        async with self._global_lock:
            bucket = self._buckets.get(storage_key)
            if bucket is None:
                bucket = DebounceBucket(storage_key, debounce_seconds)
                self._buckets[storage_key] = bucket
                log.info(
                    "debounce.bucket.created",
                    storage_key=storage_key,
                    debounce_seconds=debounce_seconds,
                )
            elif debounce_seconds != bucket.debounce_seconds:
                bucket.debounce_seconds = debounce_seconds
                log.info(
                    "debounce.bucket.updated",
                    storage_key=storage_key,
                    debounce_seconds=debounce_seconds,
                )

        async with bucket.lock:
            bucket.messages.append(msg)
            msg_count = len(bucket.messages)
            thread_id = (msg.metadata or {}).get("thread_id")
            if isinstance(thread_id, str) and thread_id.strip():
                self._thread_to_storage_key[thread_id.strip()] = storage_key

            log.info(
                "debounce.message.added",
                storage_key=storage_key,
                messages_in_bucket=msg_count,
                timer_reset=bucket.task is not None and not bucket.task.done(),
            )

            # AICODE-NOTE: Timer reset on new message (debounce pattern)
            # Cancel existing timer and start fresh - ensures silence window
            # is measured from the LAST message, not the first.
            if bucket.task and not bucket.task.done():
                bucket.task.cancel()
                try:
                    await bucket.task
                except asyncio.CancelledError:
                    pass
            bucket.task = asyncio.create_task(self._tick(bucket))

        return bucket.debounce_seconds

    async def _tick(self, bucket: DebounceBucket) -> None:
        try:
            log.info(
                "debounce.timer.started",
                storage_key=bucket.storage_key,
                wait_seconds=bucket.debounce_seconds,
            )
            await asyncio.sleep(bucket.debounce_seconds)

            async with bucket.lock:
                batch = bucket.messages[:]
                bucket.messages.clear()

            if not batch:
                log.info(
                    "debounce.timer.empty",
                    storage_key=bucket.storage_key,
                )
                return

            log.info(
                "debounce.timer.fired",
                storage_key=bucket.storage_key,
                conversation_id=batch[-1].conversation_id if batch else None,
                batch_size=len(batch),
            )

            await self._on_batch_callback(bucket.storage_key, batch)
        except Exception as exc:
            log.exception(
                "debounce.batch_failed",
                storage_key=bucket.storage_key,
                error=str(exc),
            )
        finally:
            # AICODE-NOTE: Memory cleanup - remove empty buckets after callback
            # Guards against new messages arriving during callback execution.
            # Only removes bucket if still empty (prevents premature cleanup).
            async with self._global_lock:
                if bucket.storage_key in self._buckets and not self._buckets[bucket.storage_key].messages:
                    self._buckets.pop(bucket.storage_key, None)
                    for tid, sk in list(self._thread_to_storage_key.items()):
                        if sk == bucket.storage_key:
                            del self._thread_to_storage_key[tid]
                            break
                    log.info(
                        "debounce.bucket.cleaned",
                        storage_key=bucket.storage_key,
                    )

    async def cancel_bucket_for_thread(self, thread_id: str) -> bool:
        """Cancel debounce bucket for thread. Returns True if a bucket was cancelled."""
        tid = (thread_id or "").strip()
        if not tid:
            return False
        async with self._global_lock:
            storage_key = self._thread_to_storage_key.pop(tid, None)
            if not storage_key or storage_key not in self._buckets:
                return False
            bucket = self._buckets[storage_key]
        async with bucket.lock:
            if bucket.task and not bucket.task.done():
                bucket.task.cancel()
                try:
                    await bucket.task
                except asyncio.CancelledError:
                    pass
            bucket.messages.clear()
        log.info(
            "debounce.bucket.cancelled",
            storage_key=storage_key,
            thread_id=tid,
        )
        return True
