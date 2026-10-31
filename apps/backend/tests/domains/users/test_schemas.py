"""Tests for WorkSchedule schema validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.backend.modules.users.schemas import TimeSlot, WeeklySchedule, WorkSchedule


class TestTimeSlot:
    """Test TimeSlot validation."""

    def test_valid_time_slot(self) -> None:
        slot = TimeSlot(start="09:00", end="18:00")
        assert slot.start == "09:00"
        assert slot.end == "18:00"

    def test_invalid_time_format(self) -> None:
        with pytest.raises(ValidationError):
            TimeSlot(start="25:00", end="18:00")

        with pytest.raises(ValidationError):
            TimeSlot(start="09:00", end="60:00")

        with pytest.raises(ValidationError):
            TimeSlot(start="9:00", end="18:00")

    def test_start_after_end(self) -> None:
        with pytest.raises(ValueError, match="start must be less than end"):
            TimeSlot(start="18:00", end="09:00")

    def test_start_equal_end(self) -> None:
        with pytest.raises(ValueError, match="start must be less than end"):
            TimeSlot(start="09:00", end="09:00")


class TestWeeklySchedule:
    """Test WeeklySchedule validation."""

    def test_valid_weekly_schedule(self) -> None:
        schedule = WeeklySchedule(
            mon=[TimeSlot(start="09:00", end="18:00")],
            tue=[TimeSlot(start="09:00", end="18:00")],
            wed=[TimeSlot(start="09:00", end="18:00")],
            thu=[TimeSlot(start="09:00", end="18:00")],
            fri=[TimeSlot(start="09:00", end="18:00")],
            sat=[],
            sun=[],
        )
        assert len(schedule.mon) == 1
        assert len(schedule.sat) == 0

    def test_multiple_slots_per_day_mvp(self) -> None:
        with pytest.raises(ValueError, match="must have at most one slot in MVP"):
            WeeklySchedule(
                mon=[TimeSlot(start="09:00", end="12:00"), TimeSlot(start="13:00", end="18:00")],
                tue=[],
                wed=[],
                thu=[],
                fri=[],
                sat=[],
                sun=[],
            )

    def test_all_days_empty(self) -> None:
        schedule = WeeklySchedule(
            mon=[],
            tue=[],
            wed=[],
            thu=[],
            fri=[],
            sat=[],
            sun=[],
        )
        assert len(schedule.mon) == 0


class TestWorkSchedule:
    """Test WorkSchedule validation."""

    def test_valid_work_schedule(self) -> None:
        schedule = WorkSchedule(
            version=1,
            timezone="Europe/Moscow",
            weekly=WeeklySchedule(
                mon=[TimeSlot(start="09:00", end="18:00")],
                tue=[TimeSlot(start="09:00", end="18:00")],
                wed=[TimeSlot(start="09:00", end="18:00")],
                thu=[TimeSlot(start="09:00", end="18:00")],
                fri=[TimeSlot(start="09:00", end="18:00")],
                sat=[],
                sun=[],
            ),
        )
        assert schedule.version == 1
        assert schedule.timezone == "Europe/Moscow"

    def test_invalid_timezone(self) -> None:
        with pytest.raises(ValueError, match="Invalid IANA timezone"):
            WorkSchedule(
                version=1,
                timezone="Invalid/Timezone",
                weekly=WeeklySchedule(
                    mon=[],
                    tue=[],
                    wed=[],
                    thu=[],
                    fri=[],
                    sat=[],
                    sun=[],
                ),
            )

    def test_version_less_than_one(self) -> None:
        with pytest.raises(ValidationError):
            WorkSchedule(
                version=0,
                timezone="Europe/Moscow",
                weekly=WeeklySchedule(
                    mon=[],
                    tue=[],
                    wed=[],
                    thu=[],
                    fri=[],
                    sat=[],
                    sun=[],
                ),
            )

    def test_valid_timezones(self) -> None:
        valid_timezones = ["Europe/Moscow", "America/New_York", "Asia/Tokyo", "UTC"]
        for tz in valid_timezones:
            schedule = WorkSchedule(
                version=1,
                timezone=tz,
                weekly=WeeklySchedule(
                    mon=[],
                    tue=[],
                    wed=[],
                    thu=[],
                    fri=[],
                    sat=[],
                    sun=[],
                ),
            )
            assert schedule.timezone == tz
