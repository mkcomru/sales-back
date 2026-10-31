"""Tests for company-users routers."""

from __future__ import annotations

import pytest
from fastapi import status

from src.backend.modules.companies.models import Company
from src.backend.modules.users.models import CompanyUser, User, UserRole


@pytest.fixture
async def manager_user(company: Company) -> CompanyUser:
    """Create test manager user with schedule."""
    user = await User.create(
        first_name="Manager",
        last_name="User",
        email="manager@test.com",
        hashed_password="hashed",  # pragma: allowlist secret
        is_active=True,
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
async def another_manager(company: Company) -> CompanyUser:
    """Create another manager for testing."""
    user = await User.create(
        first_name="Another",
        last_name="Manager",
        email="another@test.com",
        hashed_password="hashed",  # pragma: allowlist secret
        is_active=True,
    )
    return await CompanyUser.create(
        user=user,
        company=company,
        role=UserRole.MANAGER,
        work_schedule=None,
        is_available=False,
    )


@pytest.fixture
async def viewer_user(company: Company) -> CompanyUser:
    """Create test viewer user."""
    user = await User.create(
        first_name="Viewer",
        last_name="User",
        email="viewer@test.com",
        hashed_password="hashed",  # pragma: allowlist secret
        is_active=True,
    )
    return await CompanyUser.create(
        user=user,
        company=company,
        role=UserRole.VIEWER,
        work_schedule=None,
        is_available=True,
    )


@pytest.fixture
async def manager_headers(manager_user: CompanyUser, settings) -> dict[str, str]:
    """Generate authorization headers for manager."""
    from src.backend.modules.auth.service import AuthService

    auth_service = AuthService(settings)
    access_token = auth_service.create_access_token(manager_user.user_id, is_superuser=False)
    return {"Authorization": f"Bearer {access_token}"}


@pytest.fixture
async def viewer_headers(viewer_user: CompanyUser, settings) -> dict[str, str]:
    """Generate authorization headers for viewer."""
    from src.backend.modules.auth.service import AuthService

    auth_service = AuthService(settings)
    access_token = auth_service.create_access_token(viewer_user.user_id, is_superuser=False)
    return {"Authorization": f"Bearer {access_token}"}


@pytest.mark.asyncio
class TestUpdateCompanyUser:
    """Test PATCH /api/v1/company-users/{id} endpoint."""

    async def test_update_work_schedule(
        self, api_client, manager_user: CompanyUser, manager_headers: dict[str, str]
    ) -> None:
        """Test updating work schedule."""
        new_schedule = {
            "version": 1,
            "timezone": "UTC",
            "weekly": {
                "mon": [{"start": "10:00", "end": "19:00"}],
                "tue": [{"start": "10:00", "end": "19:00"}],
                "wed": [{"start": "10:00", "end": "19:00"}],
                "thu": [{"start": "10:00", "end": "19:00"}],
                "fri": [{"start": "10:00", "end": "19:00"}],
                "sat": [],
                "sun": [],
            },
        }

        response = await api_client.patch(
            f"/api/v1/company-users/{manager_user.id}",
            json={"work_schedule": new_schedule},
            headers=manager_headers,
        )

        if response.status_code != status.HTTP_200_OK:
            print(f"Response status: {response.status_code}")
            print(f"Response body: {response.text}")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["id"] == manager_user.id
        assert data["work_schedule"]["timezone"] == "UTC"
        assert data["work_schedule"]["weekly"]["mon"][0]["start"] == "10:00"

        await manager_user.refresh_from_db()
        assert manager_user.work_schedule["timezone"] == "UTC"

    async def test_update_is_available(
        self, api_client, manager_user: CompanyUser, manager_headers: dict[str, str]
    ) -> None:
        """Test updating is_available."""
        assert manager_user.is_available is True

        response = await api_client.patch(
            f"/api/v1/company-users/{manager_user.id}",
            json={"is_available": False},
            headers=manager_headers,
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["is_available"] is False

        await manager_user.refresh_from_db()
        assert manager_user.is_available is False

    async def test_update_both_fields(
        self, api_client, manager_user: CompanyUser, manager_headers: dict[str, str]
    ) -> None:
        """Test updating both work_schedule and is_available."""
        new_schedule = {
            "version": 1,
            "timezone": "Europe/London",
            "weekly": {
                "mon": [{"start": "08:00", "end": "17:00"}],
                "tue": [{"start": "08:00", "end": "17:00"}],
                "wed": [{"start": "08:00", "end": "17:00"}],
                "thu": [{"start": "08:00", "end": "17:00"}],
                "fri": [{"start": "08:00", "end": "17:00"}],
                "sat": [],
                "sun": [],
            },
        }

        response = await api_client.patch(
            f"/api/v1/company-users/{manager_user.id}",
            json={"work_schedule": new_schedule, "is_available": False},
            headers=manager_headers,
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["work_schedule"]["timezone"] == "Europe/London"
        assert data["is_available"] is False

        await manager_user.refresh_from_db()
        assert manager_user.work_schedule["timezone"] == "Europe/London"
        assert manager_user.is_available is False

    async def test_update_company_user_not_found(self, api_client, manager_headers: dict[str, str]) -> None:
        """Test updating non-existent company user."""
        response = await api_client.patch(
            "/api/v1/company-users/99999",
            json={"is_available": False},
            headers=manager_headers,
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    async def test_update_company_user_different_company(
        self, api_client, manager_user: CompanyUser, manager_headers: dict[str, str], company_factory
    ) -> None:
        """Test updating company user from different company."""
        other_company = await company_factory(name="Other Company")
        other_user = await User.create(
            first_name="Other",
            last_name="User",
            email="other@test.com",
            hashed_password="hashed",  # pragma: allowlist secret
            is_active=True,
        )
        other_company_user = await CompanyUser.create(
            user=other_user,
            company=other_company,
            role=UserRole.MANAGER,
        )

        response = await api_client.patch(
            f"/api/v1/company-users/{other_company_user.id}",
            json={"is_available": False},
            headers=manager_headers,
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    async def test_update_requires_manager_role(
        self, api_client, manager_user: CompanyUser, viewer_headers: dict[str, str]
    ) -> None:
        """Test that viewer cannot update company user."""
        response = await api_client.patch(
            f"/api/v1/company-users/{manager_user.id}",
            json={"is_available": False},
            headers=viewer_headers,
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    async def test_update_unauthorized(self, api_client, manager_user: CompanyUser) -> None:
        """Test updating without authentication."""
        response = await api_client.patch(
            f"/api/v1/company-users/{manager_user.id}",
            json={"is_available": False},
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_update_invalid_schedule(
        self, api_client, manager_user: CompanyUser, manager_headers: dict[str, str]
    ) -> None:
        """Test updating with invalid schedule."""
        invalid_schedule = {
            "version": 1,
            "timezone": "Invalid/Timezone",
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

        response = await api_client.patch(
            f"/api/v1/company-users/{manager_user.id}",
            json={"work_schedule": invalid_schedule},
            headers=manager_headers,
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.asyncio
class TestGetCompanyUserSchedule:
    """Test GET /api/v1/company-users/{id}/schedule endpoint."""

    async def test_get_schedule_success(
        self, api_client, manager_user: CompanyUser, manager_headers: dict[str, str]
    ) -> None:
        """Test getting schedule with interpretation."""
        response = await api_client.get(
            f"/api/v1/company-users/{manager_user.id}/schedule",
            headers=manager_headers,
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "work_schedule" in data
        assert "is_available" in data
        assert "schedule_description" in data
        assert "is_working_now" in data
        assert "next_available_at" in data
        assert "next_available_at_local" in data
        assert "next_available_timezone" in data
        assert data["work_schedule"]["timezone"] == "Europe/Moscow"
        assert data["is_available"] is True

    async def test_get_schedule_no_schedule(
        self, api_client, another_manager: CompanyUser, manager_headers: dict[str, str]
    ) -> None:
        """Test getting schedule for user without schedule."""
        response = await api_client.get(
            f"/api/v1/company-users/{another_manager.id}/schedule",
            headers=manager_headers,
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["work_schedule"] is None
        assert data["schedule_description"] is None
        assert data["is_working_now"] is False

    async def test_get_schedule_not_found(self, api_client, manager_headers: dict[str, str]) -> None:
        """Test getting schedule for non-existent user."""
        response = await api_client.get(
            "/api/v1/company-users/99999/schedule",
            headers=manager_headers,
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    async def test_get_schedule_different_company(
        self, api_client, manager_user: CompanyUser, manager_headers: dict[str, str], company_factory
    ) -> None:
        """Test getting schedule for user from different company."""
        other_company = await company_factory(name="Other Company")
        other_user = await User.create(
            first_name="Other",
            last_name="User",
            email="other@test.com",
            hashed_password="hashed",  # pragma: allowlist secret
            is_active=True,
        )
        other_company_user = await CompanyUser.create(
            user=other_user,
            company=other_company,
            role=UserRole.MANAGER,
        )

        response = await api_client.get(
            f"/api/v1/company-users/{other_company_user.id}/schedule",
            headers=manager_headers,
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    async def test_get_schedule_viewer_access(
        self, api_client, manager_user: CompanyUser, viewer_headers: dict[str, str]
    ) -> None:
        """Test that viewer can get schedule."""
        response = await api_client.get(
            f"/api/v1/company-users/{manager_user.id}/schedule",
            headers=viewer_headers,
        )

        assert response.status_code == status.HTTP_200_OK

    async def test_get_schedule_unauthorized(self, api_client, manager_user: CompanyUser) -> None:
        """Test getting schedule without authentication."""
        response = await api_client.get(f"/api/v1/company-users/{manager_user.id}/schedule")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
class TestGetAvailableManagers:
    """Test GET /api/v1/companies/{id}/available-managers endpoint."""

    async def test_get_available_managers_success(
        self, api_client, company: Company, manager_user: CompanyUser, manager_headers: dict[str, str]
    ) -> None:
        """Test getting list of available managers."""
        response = await api_client.get(
            f"/api/v1/companies/{company.id}/available-managers",
            headers=manager_headers,
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1

        manager_data = next(m for m in data if m["id"] == manager_user.id)
        assert manager_data["user_id"] == manager_user.user_id
        assert manager_data["name"] == "Manager User"
        assert manager_data["email"] == "manager@test.com"
        assert manager_data["role"] == "manager"
        assert manager_data["is_available"] is True
        assert "is_working_now" in manager_data
        assert "schedule_description" in manager_data
        assert "next_available_at" in manager_data
        assert "next_available_at_local" in manager_data
        assert "last_assigned_at" in manager_data

    async def test_get_available_managers_excludes_unavailable(
        self,
        api_client,
        company: Company,
        manager_user: CompanyUser,
        another_manager: CompanyUser,
        manager_headers: dict[str, str],
    ) -> None:
        """Test that unavailable managers are excluded."""
        response = await api_client.get(
            f"/api/v1/companies/{company.id}/available-managers",
            headers=manager_headers,
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        manager_ids = [m["id"] for m in data]
        assert manager_user.id in manager_ids
        assert another_manager.id not in manager_ids

    async def test_get_available_managers_excludes_viewers(
        self,
        api_client,
        company: Company,
        manager_user: CompanyUser,
        viewer_user: CompanyUser,
        manager_headers: dict[str, str],
    ) -> None:
        """Test that viewers are excluded from available managers."""
        response = await api_client.get(
            f"/api/v1/companies/{company.id}/available-managers",
            headers=manager_headers,
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        manager_ids = [m["id"] for m in data]
        assert manager_user.id in manager_ids
        assert viewer_user.id not in manager_ids

    async def test_get_available_managers_empty(
        self, api_client, company: Company, manager_headers: dict[str, str]
    ) -> None:
        """Test getting available managers when none exist."""
        await CompanyUser.filter(company_id=company.id).update(is_available=False)

        response = await api_client.get(
            f"/api/v1/companies/{company.id}/available-managers",
            headers=manager_headers,
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data == []

    async def test_get_available_managers_not_found(self, api_client, manager_headers: dict[str, str]) -> None:
        """Test getting available managers for non-existent company."""
        response = await api_client.get(
            "/api/v1/companies/99999/available-managers",
            headers=manager_headers,
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    async def test_get_available_managers_viewer_access(
        self, api_client, company: Company, manager_user: CompanyUser, viewer_headers: dict[str, str]
    ) -> None:
        """Test that viewer can get available managers."""
        response = await api_client.get(
            f"/api/v1/companies/{company.id}/available-managers",
            headers=viewer_headers,
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert isinstance(data, list)

    async def test_get_available_managers_unauthorized(self, api_client, company: Company) -> None:
        """Test getting available managers without authentication."""
        response = await api_client.get(f"/api/v1/companies/{company.id}/available-managers")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
