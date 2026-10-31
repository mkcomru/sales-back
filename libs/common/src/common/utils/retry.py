"""Retry utilities with configurable backoff strategies."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import structlog

log = structlog.get_logger(__name__)


class RetryStrategy:
    """Retry strategy configuration."""

    def __init__(
        self,
        max_attempts: int = 3,
        base_delay_s: float = 1.0,
        backoff_type: str = "exponential",
        max_delay_s: float | None = None,
    ):
        """Initialize retry strategy.

        Args:
            max_attempts: Maximum number of retry attempts
            base_delay_s: Base delay in seconds for backoff calculation
            backoff_type: "linear" or "exponential"
            max_delay_s: Maximum delay cap (None for no cap)
        """
        self.max_attempts = max_attempts
        self.base_delay_s = base_delay_s
        self.backoff_type = backoff_type
        self.max_delay_s = max_delay_s

    def calculate_delay(self, attempt: int) -> float:
        """Calculate delay for given attempt number (1-based).

        Args:
            attempt: Attempt number (1-based, so attempt 1 = first retry)

        Returns:
            Delay in seconds
        """
        if self.backoff_type == "linear":
            delay = self.base_delay_s * attempt
        elif self.backoff_type == "exponential":
            delay = self.base_delay_s * (2 ** (attempt - 1))
        else:
            delay = self.base_delay_s

        if self.max_delay_s is not None:
            delay = min(delay, self.max_delay_s)

        return delay


async def retry_with_backoff[T](
    func: Callable[..., Awaitable[T]],
    *args: Any,
    strategy: RetryStrategy | None = None,
    retry_on: Callable[[Exception], bool] | None = None,
    log_context: dict[str, Any] | None = None,
    **kwargs: Any,
) -> T:
    """Execute async function with retry logic and backoff.

    Args:
        func: Async function to execute
        *args: Positional arguments for func
        strategy: Retry strategy configuration (default: 3 attempts, exponential backoff)
        retry_on: Callable that returns True if exception should trigger retry
        log_context: Additional context for logging
        **kwargs: Keyword arguments for func

    Returns:
        Result of func execution

    Raises:
        Last exception if all retries are exhausted
    """
    if strategy is None:
        strategy = RetryStrategy()

    if log_context is None:
        log_context = {}

    last_error: Exception | None = None

    for attempt in range(1, strategy.max_attempts + 1):
        try:
            result = await func(*args, **kwargs)
            if attempt > 1:
                log.info(
                    "retry.succeeded",
                    attempt=attempt,
                    max_attempts=strategy.max_attempts,
                    **log_context,
                )
            return result
        except Exception as e:
            last_error = e

            if retry_on is not None and not retry_on(e):
                log.debug(
                    "retry.skipped",
                    attempt=attempt,
                    error_type=type(e).__name__,
                    error=str(e),
                    **log_context,
                )
                raise

            if attempt >= strategy.max_attempts:
                log.error(
                    "retry.exhausted",
                    attempt=attempt,
                    max_attempts=strategy.max_attempts,
                    error_type=type(e).__name__,
                    error=str(e),
                    **log_context,
                )
                raise

            delay = strategy.calculate_delay(attempt)
            log.warning(
                "retry.attempt_failed",
                attempt=attempt,
                max_attempts=strategy.max_attempts,
                delay_s=delay,
                error_type=type(e).__name__,
                error=str(e),
                **log_context,
            )

            await asyncio.sleep(delay)

    raise RuntimeError("Retry loop exhausted without return or raise") from last_error
