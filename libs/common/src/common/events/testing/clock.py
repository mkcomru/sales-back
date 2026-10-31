"""Fake clock for deterministic testing."""

from datetime import UTC, datetime, timedelta


class FakeClock:
    """
    Fake clock for testing time-dependent behavior.

    Provides:
    - Deterministic time progression
    - Manual time advancement
    - No-wait sleep implementation
    """

    def __init__(self, start: datetime | None = None) -> None:
        self._current = start or datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        self._sleep_calls: list[float] = []

    def now(self) -> datetime:
        """Get current fake time."""
        return self._current

    def advance(self, seconds: float) -> None:
        """Advance clock by given seconds."""
        self._current += timedelta(seconds=seconds)

    def set(self, dt: datetime) -> None:
        """Set clock to specific datetime."""
        self._current = dt

    async def sleep(self, seconds: float) -> None:
        """Record sleep call and advance clock (no actual waiting)."""
        self._sleep_calls.append(seconds)
        self.advance(seconds)

    @property
    def sleep_calls(self) -> list[float]:
        """Get list of sleep durations requested."""
        return self._sleep_calls.copy()

    def reset_sleep_calls(self) -> None:
        """Clear recorded sleep calls."""
        self._sleep_calls.clear()
