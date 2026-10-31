"""Tests for RateLimiter."""

import time

import pytest

from common.sync.rate_limiter import RateLimiter


@pytest.mark.asyncio
async def test_acquire_respects_rate_limit():
    """Test that acquire respects rate limit."""
    limiter = RateLimiter(rate=2.0)  # 2 req/sec = 0.5s delay

    start = time.time()
    await limiter.acquire()
    await limiter.acquire()
    elapsed = time.time() - start

    # Should take at least 0.5 seconds between requests
    assert elapsed >= 0.4  # Allow some tolerance


@pytest.mark.asyncio
async def test_on_success_resets_backoff():
    """Test that on_success resets backoff after rate limit."""
    limiter = RateLimiter(rate=2.0)
    limiter.on_rate_limit()
    assert limiter.current_delay > limiter.min_delay

    limiter.on_success()
    assert limiter.current_delay == limiter.min_delay
    assert limiter._consecutive_429 == 0


@pytest.mark.asyncio
async def test_on_rate_limit_increases_backoff():
    """Test that on_rate_limit increases backoff exponentially."""
    limiter = RateLimiter(rate=2.0)
    initial_delay = limiter.current_delay

    limiter.on_rate_limit()
    assert limiter.current_delay == initial_delay * 2.0

    limiter.on_rate_limit()
    assert limiter.current_delay == initial_delay * 4.0


@pytest.mark.asyncio
async def test_reset():
    """Test that reset restores initial state."""
    limiter = RateLimiter(rate=2.0)
    limiter.on_rate_limit()
    limiter.on_rate_limit()

    limiter.reset()
    assert limiter.current_delay == limiter.min_delay
    assert limiter._backoff_multiplier == 1.0
    assert limiter._consecutive_429 == 0
