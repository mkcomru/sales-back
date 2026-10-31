"""Rate limiter for sync API calls."""

import asyncio
import time

import structlog

log = structlog.get_logger(__name__)


class RateLimiter:
    """Rate limiter with exponential backoff for 429 errors.

    Uses token bucket algorithm to limit request rate.
    Automatically increases delay after 429 errors.
    """

    def __init__(self, rate: float, initial_delay: float = 0.0):
        """Initialize rate limiter.

        Args:
            rate: Requests per second
            initial_delay: Initial delay between requests (seconds)
        """
        self.rate = rate
        self.min_delay = 1.0 / rate if rate > 0 else 0.0
        self.current_delay = max(initial_delay, self.min_delay)
        self._last_request_time = 0.0
        self._backoff_multiplier = 1.0
        self._consecutive_429 = 0

    async def acquire(self) -> None:
        """Acquire permission to make a request (rate limiting).

        Waits if necessary to respect rate limit.
        """
        now = time.time()
        elapsed = now - self._last_request_time

        if elapsed < self.current_delay:
            wait_time = self.current_delay - elapsed
            await asyncio.sleep(wait_time)

        self._last_request_time = time.time()

    def on_success(self) -> None:
        """Called after successful request to reset backoff."""
        if self._consecutive_429 > 0:
            log.debug(
                "rate_limiter.backoff_reset",
                consecutive_429=self._consecutive_429,
            )
            self._consecutive_429 = 0
            self._backoff_multiplier = 1.0
            self.current_delay = self.min_delay

    def on_rate_limit(self) -> None:
        """Called when 429 rate limit error occurs.

        Increases backoff delay exponentially.
        """
        self._consecutive_429 += 1
        self._backoff_multiplier *= 2.0
        self.current_delay = self.min_delay * self._backoff_multiplier

        log.warning(
            "rate_limiter.backoff_increased",
            consecutive_429=self._consecutive_429,
            current_delay=self.current_delay,
            backoff_multiplier=self._backoff_multiplier,
        )

    def reset(self) -> None:
        """Reset rate limiter to initial state."""
        self.current_delay = self.min_delay
        self._backoff_multiplier = 1.0
        self._consecutive_429 = 0
        self._last_request_time = 0.0
