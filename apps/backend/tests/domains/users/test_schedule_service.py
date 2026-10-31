"""Tests for ScheduleService."""

from __future__ import annotations

from datetime import datetime

import pytest

from src.backend.modules.companies.models import Company
from src.backend.modules.users.models import CompanyUser, User, UserRole
from src.backend.modules.users.schedule_service import schedule_service


@pytest.fixture
async def test_company(company_factory) -> Company:
    """Create test company."""
    return await company_factory(name="Test Company")


@pytest.fixture
async def test_user() -> User:
    """Create test user."""
    return await User.create(
        first_name="Test",
        last_name="User",
        email="test@example.com",
        hashed_password="hashed",  # pragma: allowlist secret
        is_active=True,
    )


@pytest.fixture
async def company_user_with_schedule(test_company: Company, test_user: User) -> CompanyUser:
    """Create company user with work schedule."""
    work_schedule = {
        "version": 1,
        "timezone": "Europe/Moscow",
        "weekly": {
            "mon": [{"start": "09:00", "end": "18:00"}],
            "tue": [{"start": "09:00", "end": "18:00"}],
            "wed": [{"start": "09:00", "end": "18:00"}],
            "thu": [{"start": "09:00", "end": "18:00"}],
            "fri": [{"start": "09:00", "end": "18:00"}],
            "sat": [],
            "sun": [],
        },
    }
    return await CompanyUser.create(
        user=test_user,
        company=test_company,
        role=UserRole.MANAGER,
        work_schedule=work_schedule,
        is_available=True,
    )


@pytest.fixture
async def company_user_without_schedule(test_company: Company, test_user: User) -> CompanyUser:
    """Create company user without work schedule."""
    return await CompanyUser.create(
        user=test_user,
        company=test_company,
        role=UserRole.MANAGER,
        work_schedule=None,
        is_available=True,
    )


@pytest.mark.asyncio
class TestIsManagerWorkingNow:
    """Test is_manager_working_now method."""

    async def test_manager_working_now_weekday_working_hours(self, company_user_with_schedule: CompanyUser) -> None:
        result = schedule_service.is_manager_working_now(company_user_with_schedule)
        assert isinstance(result, bool)

    async def test_manager_not_working_no_schedule(self, company_user_without_schedule: CompanyUser) -> None:
        result = schedule_service.is_manager_working_now(company_user_without_schedule)
        assert result is False

    async def test_manager_not_available(self, company_user_with_schedule: CompanyUser) -> None:
        company_user_with_schedule.is_available = False
        await company_user_with_schedule.save(update_fields=["is_available"])

        result = schedule_service.is_manager_working_now(company_user_with_schedule)
        assert result is False

    async def test_manager_weekend(self, company_user_with_schedule: CompanyUser) -> None:
        work_schedule = {
            "version": 1,
            "timezone": "Europe/Moscow",
            "weekly": {
                "mon": [],
                "tue": [],
                "wed": [],
                "thu": [],
                "fri": [],
                "sat": [],
                "sun": [],
            },
        }
        company_user_with_schedule.work_schedule = work_schedule
        await company_user_with_schedule.save(update_fields=["work_schedule"])

        result = schedule_service.is_manager_working_now(company_user_with_schedule)
        assert result is False


@pytest.mark.asyncio
class TestGetNextWorkingTime:
    """Test get_next_working_time method."""

    async def test_get_next_working_time_with_schedule(self, company_user_with_schedule: CompanyUser) -> None:
        result = schedule_service.get_next_working_time(company_user_with_schedule)
        assert result is None or isinstance(result, datetime)

    async def test_get_next_working_time_no_schedule(self, company_user_without_schedule: CompanyUser) -> None:
        result = schedule_service.get_next_working_time(company_user_without_schedule)
        assert result is None

    async def test_get_next_working_time_all_days_empty(self, company_user_with_schedule: CompanyUser) -> None:
        work_schedule = {
            "version": 1,
            "timezone": "Europe/Moscow",
            "weekly": {
                "mon": [],
                "tue": [],
                "wed": [],
                "thu": [],
                "fri": [],
                "sat": [],
                "sun": [],
            },
        }
        company_user_with_schedule.work_schedule = work_schedule
        await company_user_with_schedule.save(update_fields=["work_schedule"])

        result = schedule_service.get_next_working_time(company_user_with_schedule)
        assert result is None


@pytest.mark.asyncio
class TestGetAvailableManagers:
    """Test get_available_managers method."""

    async def test_get_available_managers_excludes_viewer(self, test_company: Company, test_user: User) -> None:
        manager = await CompanyUser.create(
            user=test_user,
            company=test_company,
            role=UserRole.MANAGER,
            work_schedule={
                "version": 1,
                "timezone": "Europe/Moscow",
                "weekly": {"mon": [], "tue": [], "wed": [], "thu": [], "fri": [], "sat": [], "sun": []},
            },
            is_available=True,
        )

        viewer = await CompanyUser.create(
            user=await User.create(
                first_name="Viewer",
                last_name="User",
                email="viewer@example.com",
                hashed_password="hashed",  # pragma: allowlist secret
            ),
            company=test_company,
            role=UserRole.VIEWER,
            work_schedule={
                "version": 1,
                "timezone": "Europe/Moscow",
                "weekly": {"mon": [], "tue": [], "wed": [], "thu": [], "fri": [], "sat": [], "sun": []},
            },
            is_available=True,
        )

        managers = await schedule_service.get_available_managers(test_company)
        manager_ids = {m.id for m in managers}
        assert manager.id in manager_ids
        assert viewer.id not in manager_ids

    async def test_get_available_managers_filters_by_availability(self, test_company: Company, test_user: User) -> None:
        available = await CompanyUser.create(
            user=test_user,
            company=test_company,
            role=UserRole.MANAGER,
            work_schedule={
                "version": 1,
                "timezone": "Europe/Moscow",
                "weekly": {"mon": [], "tue": [], "wed": [], "thu": [], "fri": [], "sat": [], "sun": []},
            },
            is_available=True,
        )

        unavailable = await CompanyUser.create(
            user=await User.create(
                first_name="Unavailable",
                last_name="User",
                email="unavailable@example.com",
                hashed_password="hashed",  # pragma: allowlist secret
            ),
            company=test_company,
            role=UserRole.MANAGER,
            work_schedule={
                "version": 1,
                "timezone": "Europe/Moscow",
                "weekly": {"mon": [], "tue": [], "wed": [], "thu": [], "fri": [], "sat": [], "sun": []},
            },
            is_available=False,
        )

        managers = await schedule_service.get_available_managers(test_company)
        manager_ids = {m.id for m in managers}
        assert available.id in manager_ids
        assert unavailable.id not in manager_ids

    async def test_get_available_managers_filters_by_schedule(self, test_company: Company, test_user: User) -> None:
        with_schedule = await CompanyUser.create(
            user=test_user,
            company=test_company,
            role=UserRole.MANAGER,
            work_schedule={
                "version": 1,
                "timezone": "Europe/Moscow",
                "weekly": {"mon": [], "tue": [], "wed": [], "thu": [], "fri": [], "sat": [], "sun": []},
            },
            is_available=True,
        )

        without_schedule = await CompanyUser.create(
            user=await User.create(
                first_name="NoSchedule",
                last_name="User",
                email="noschedule@example.com",
                hashed_password="hashed",  # pragma: allowlist secret
            ),
            company=test_company,
            role=UserRole.MANAGER,
            work_schedule=None,
            is_available=True,
        )

        managers = await schedule_service.get_available_managers(test_company)
        manager_ids = {m.id for m in managers}
        assert with_schedule.id in manager_ids
        assert without_schedule.id not in manager_ids


@pytest.mark.asyncio
class TestScheduleDescription:
    """Test schedule_description method."""

    async def test_schedule_description_weekdays(self, company_user_with_schedule: CompanyUser) -> None:
        result = schedule_service.schedule_description(company_user_with_schedule)
        assert result is not None
        assert "Пн-Пт" in result or "09:00-18:00" in result
        assert "Europe/Moscow" in result

    async def test_schedule_description_no_schedule(self, company_user_without_schedule: CompanyUser) -> None:
        result = schedule_service.schedule_description(company_user_without_schedule)
        assert result is None

    async def test_schedule_description_all_days_empty(self, company_user_with_schedule: CompanyUser) -> None:
        work_schedule = {
            "version": 1,
            "timezone": "Europe/Moscow",
            "weekly": {
                "mon": [],
                "tue": [],
                "wed": [],
                "thu": [],
                "fri": [],
                "sat": [],
                "sun": [],
            },
        }
        company_user_with_schedule.work_schedule = work_schedule
        await company_user_with_schedule.save(update_fields=["work_schedule"])

        result = schedule_service.schedule_description(company_user_with_schedule)
        assert result is None

    async def test_schedule_description_single_day(self, test_company: Company, test_user: User) -> None:
        work_schedule = {
            "version": 1,
            "timezone": "Europe/Moscow",
            "weekly": {
                "mon": [{"start": "10:00", "end": "19:00"}],
                "tue": [],
                "wed": [],
                "thu": [],
                "fri": [],
                "sat": [],
                "sun": [],
            },
        }
        company_user = await CompanyUser.create(
            user=test_user,
            company=test_company,
            role=UserRole.MANAGER,
            work_schedule=work_schedule,
        )

        result = schedule_service.schedule_description(company_user)
        assert result is not None
        assert "Пн" in result
        assert "10:00-19:00" in result
