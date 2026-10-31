"""Tests for load balancing functionality."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from src.backend.modules.companies.models import Company
from src.backend.modules.orders.load_balancing import load_score, select_manager
from src.backend.modules.orders.models import Order
from src.backend.modules.users.models import CompanyUser, User, UserRole
from src.backend.modules.users.schedule_service import schedule_service


@pytest.fixture
async def customer(company: Company):
    """Create test customer."""
    from src.backend.modules.chat.models import Customer

    return await Customer.create(
        user_id="test-customer",
        company_id=company.id,
        name="Test Customer",
        meta={},
    )


@pytest.fixture
async def manager1(company: Company) -> CompanyUser:
    """Create first manager."""
    user = await User.create(
        first_name="Manager",
        last_name="One",
        email="manager1@test.com",
        hashed_password="hashed",  # pragma: allowlist secret
    )
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
        user=user,
        company=company,
        role=UserRole.MANAGER,
        work_schedule=work_schedule,
        is_available=True,
    )


@pytest.fixture
async def manager2(company: Company) -> CompanyUser:
    """Create second manager."""
    user = await User.create(
        first_name="Manager",
        last_name="Two",
        email="manager2@test.com",
        hashed_password="hashed",  # pragma: allowlist secret
    )
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
        user=user,
        company=company,
        role=UserRole.MANAGER,
        work_schedule=work_schedule,
        is_available=True,
    )


@pytest.mark.asyncio
class TestLoadScore:
    """Test load_score function."""

    async def test_load_score_no_orders(self, manager1: CompanyUser) -> None:
        score = await load_score(manager1)
        assert score == 0

    async def test_load_score_with_active_orders(self, manager1: CompanyUser, company: Company, customer) -> None:
        await Order.create(
            order_number=1,
            customer=customer,
            company=company,
            assignee=manager1,
            closed_at=None,
        )
        await Order.create(
            order_number=2,
            customer=customer,
            company=company,
            assignee=manager1,
            closed_at=None,
        )

        score = await load_score(manager1)
        assert score == 2

    async def test_load_score_excludes_closed_orders(self, manager1: CompanyUser, company: Company, customer) -> None:
        await Order.create(
            order_number=1,
            customer=customer,
            company=company,
            assignee=manager1,
            closed_at=None,
        )
        await Order.create(
            order_number=2,
            customer=customer,
            company=company,
            assignee=manager1,
            closed_at=datetime.now(UTC),
        )

        score = await load_score(manager1)
        assert score == 1


@pytest.mark.asyncio
class TestSelectManager:
    """Test select_manager function."""

    async def test_select_manager_chooses_less_loaded(
        self, company: Company, manager1: CompanyUser, manager2: CompanyUser, customer
    ) -> None:
        await Order.create(
            order_number=1,
            customer=customer,
            company=company,
            assignee=manager1,
            closed_at=None,
        )
        await Order.create(
            order_number=2,
            customer=customer,
            company=company,
            assignee=manager1,
            closed_at=None,
        )

        selected = await select_manager(company)
        assert selected is not None
        assert selected.id == manager2.id

    async def test_select_manager_tie_breaking_by_last_assigned(
        self, company: Company, manager1: CompanyUser, manager2: CompanyUser
    ) -> None:
        manager1.last_assigned_at = datetime.now(UTC) - timedelta(hours=2)
        await manager1.save(update_fields=["last_assigned_at"])

        manager2.last_assigned_at = None
        await manager2.save(update_fields=["last_assigned_at"])

        selected = await select_manager(company)
        assert selected is not None
        assert selected.id == manager2.id

    async def test_select_manager_no_available_managers(self, company: Company) -> None:
        selected = await select_manager(company)
        assert selected is None

    async def test_select_manager_excludes_viewer(self, company: Company, manager1: CompanyUser) -> None:
        user = await User.create(
            first_name="Viewer",
            last_name="User",
            email="viewer@test.com",
            hashed_password="hashed",  # pragma: allowlist secret
        )
        viewer = await CompanyUser.create(
            user=user,
            company=company,
            role=UserRole.VIEWER,
            work_schedule={
                "version": 1,
                "timezone": "Europe/Moscow",
                "weekly": {
                    "mon": [{"start": "09:00", "end": "18:00"}],
                    "tue": [],
                    "wed": [],
                    "thu": [],
                    "fri": [],
                    "sat": [],
                    "sun": [],
                },
            },
            is_available=True,
        )

        selected = await select_manager(company)
        assert selected is not None
        assert selected.id == manager1.id
        assert selected.id != viewer.id

    async def test_select_manager_prefers_working_over_non_working(
        self, company: Company, manager1: CompanyUser, manager2: CompanyUser
    ) -> None:
        work_schedule_off_hours = {
            "version": 1,
            "timezone": "Europe/Moscow",
            "weekly": {
                "mon": [{"start": "00:00", "end": "01:00"}],
                "tue": [],
                "wed": [],
                "thu": [],
                "fri": [],
                "sat": [],
                "sun": [],
            },
        }
        manager2.work_schedule = work_schedule_off_hours
        await manager2.save(update_fields=["work_schedule"])

        selected = await select_manager(company)
        assert selected is not None
        working_now = schedule_service.is_manager_working_now(selected)
        if working_now:
            assert selected.id == manager1.id
