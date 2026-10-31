"""Tests for users routers."""

from __future__ import annotations

import httpx
import pytest
from fastapi import status

from src.backend.modules.chat.models import Customer, Thread, ThreadState
from src.backend.modules.users.models import CompanyUser, UserRole

pytestmark = pytest.mark.asyncio


class TestGetCurrentUserInfo:
    """Test GET /users/me endpoint."""

    async def test_get_me_basic(
        self,
        api_client: httpx.AsyncClient,
        authenticated_user_with_company: dict,
    ) -> None:
        """Test basic /users/me response."""
        headers = authenticated_user_with_company["headers"]
        user = authenticated_user_with_company["user"]

        response = await api_client.get("/api/v1/users/me", headers=headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data["id"] == user.id
        assert "first_name" in data
        assert "last_name" in data
        assert data["email"] == user.email
        assert data["is_active"] is True
        assert data["is_superuser"] is False
        assert "created_at" in data
        assert "updated_at" in data
        assert "companies" in data

    async def test_get_me_unauthorized(self, api_client: httpx.AsyncClient) -> None:
        """Test /users/me without authentication."""
        response = await api_client.get("/api/v1/users/me")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_get_me_with_companies(
        self,
        api_client: httpx.AsyncClient,
        authenticated_user_with_company: dict,
        company_factory,
    ) -> None:
        """Test /users/me returns user companies."""
        headers = authenticated_user_with_company["headers"]
        user = authenticated_user_with_company["user"]
        company1 = authenticated_user_with_company["company"]

        company2 = await company_factory(name="Second Company")
        await CompanyUser.create(
            user=user,
            company=company2,
            role=UserRole.VIEWER,
        )

        response = await api_client.get("/api/v1/users/me", headers=headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert len(data["companies"]) == 2
        company_ids = {c["company_id"] for c in data["companies"]}
        assert company1.id in company_ids
        assert company2.id in company_ids

        admin_company = next(c for c in data["companies"] if c["company_id"] == company1.id)
        assert admin_company["role"] == "admin"

        viewer_company = next(c for c in data["companies"] if c["company_id"] == company2.id)
        assert viewer_company["role"] == "viewer"

    async def test_get_me_no_companies(
        self,
        api_client: httpx.AsyncClient,
        settings,
    ) -> None:
        """Test /users/me for user without companies."""
        from passlib.context import CryptContext

        from src.backend.modules.auth.service import AuthService
        from src.backend.modules.users.models import User

        pwd_context = CryptContext(schemes=["bcrypt"], bcrypt__rounds=4, deprecated="auto")
        hashed_password = pwd_context.hash("test_password_123")

        user = await User.create(
            first_name="No",
            last_name="Companies",
            email="no_companies@example.com",
            hashed_password=hashed_password,
            is_active=True,
            is_superuser=False,
        )

        auth_service = AuthService(settings)
        access_token = auth_service.create_access_token(user.id, is_superuser=False)
        headers = {"Authorization": f"Bearer {access_token}"}

        response = await api_client.get("/api/v1/users/me", headers=headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data["id"] == user.id
        assert data["first_name"] == "No"
        assert data["last_name"] == "Companies"
        assert len(data["companies"]) == 0

    async def test_get_me_superuser(
        self,
        api_client: httpx.AsyncClient,
        test_superuser,
        settings,
    ) -> None:
        """Test /users/me for superuser."""
        from src.backend.modules.auth.service import AuthService

        auth_service = AuthService(settings)
        access_token = auth_service.create_access_token(test_superuser.id, is_superuser=True)
        headers = {"Authorization": f"Bearer {access_token}"}

        response = await api_client.get("/api/v1/users/me", headers=headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data["id"] == test_superuser.id
        assert "first_name" in data
        assert "last_name" in data
        assert data["is_superuser"] is True
        assert data["email"] == test_superuser.email


class TestUpdateCurrentUserInfo:
    """Test PATCH /users/me endpoint."""

    async def test_update_first_name(
        self,
        api_client: httpx.AsyncClient,
        authenticated_user_with_company: dict,
    ) -> None:
        """Test updating first name."""
        headers = authenticated_user_with_company["headers"]
        user = authenticated_user_with_company["user"]

        payload = {"first_name": "UpdatedName"}
        response = await api_client.patch("/api/v1/users/me", json=payload, headers=headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data["id"] == user.id
        assert data["first_name"] == "UpdatedName"
        assert data["last_name"] == user.last_name
        assert data["email"] == user.email

        await user.refresh_from_db()
        assert user.first_name == "UpdatedName"

    async def test_update_last_name(
        self,
        api_client: httpx.AsyncClient,
        authenticated_user_with_company: dict,
    ) -> None:
        """Test updating last name."""
        headers = authenticated_user_with_company["headers"]
        user = authenticated_user_with_company["user"]

        payload = {"last_name": "UpdatedLastName"}
        response = await api_client.patch("/api/v1/users/me", json=payload, headers=headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data["id"] == user.id
        assert data["first_name"] == user.first_name
        assert data["last_name"] == "UpdatedLastName"

        await user.refresh_from_db()
        assert user.last_name == "UpdatedLastName"

    async def test_update_email(
        self,
        api_client: httpx.AsyncClient,
        authenticated_user_with_company: dict,
    ) -> None:
        """Test updating email."""
        headers = authenticated_user_with_company["headers"]
        user = authenticated_user_with_company["user"]

        new_email = "newemail@example.com"
        payload = {"email": new_email}
        response = await api_client.patch("/api/v1/users/me", json=payload, headers=headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data["email"] == new_email

        await user.refresh_from_db()
        assert user.email == new_email

    async def test_update_email_case_insensitive(
        self,
        api_client: httpx.AsyncClient,
        authenticated_user_with_company: dict,
    ) -> None:
        """Test that email is stored in lowercase."""
        headers = authenticated_user_with_company["headers"]
        user = authenticated_user_with_company["user"]

        new_email = "NewEmail@Example.COM"
        payload = {"email": new_email}
        response = await api_client.patch("/api/v1/users/me", json=payload, headers=headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data["email"] == new_email.lower()

        await user.refresh_from_db()
        assert user.email == new_email.lower()

    async def test_update_email_duplicate(
        self,
        api_client: httpx.AsyncClient,
        authenticated_user_with_company: dict,
    ) -> None:
        """Test that updating to an existing email fails."""
        from passlib.context import CryptContext

        from src.backend.modules.users.models import User

        headers = authenticated_user_with_company["headers"]

        pwd_context = CryptContext(schemes=["bcrypt"], bcrypt__rounds=4, deprecated="auto")
        existing_user = await User.create(
            first_name="Existing",
            last_name="User",
            email="existing@example.com",
            hashed_password=pwd_context.hash("password123"),
            is_active=True,
        )

        payload = {"email": existing_user.email}
        response = await api_client.patch("/api/v1/users/me", json=payload, headers=headers)

        assert response.status_code == status.HTTP_409_CONFLICT

    async def test_update_password(
        self,
        api_client: httpx.AsyncClient,
        authenticated_user_with_company: dict,
    ) -> None:
        """Test updating password."""
        from passlib.context import CryptContext

        headers = authenticated_user_with_company["headers"]
        user = authenticated_user_with_company["user"]

        old_hashed_password = user.hashed_password
        new_password = "newpassword123"  # pragma: allowlist secret

        payload = {"password": new_password}
        response = await api_client.patch("/api/v1/users/me", json=payload, headers=headers)

        assert response.status_code == status.HTTP_200_OK

        await user.refresh_from_db()
        assert user.hashed_password != old_hashed_password

        pwd_context = CryptContext(schemes=["bcrypt"], bcrypt__rounds=4, deprecated="auto")
        assert pwd_context.verify(new_password, user.hashed_password)

    async def test_update_multiple_fields(
        self,
        api_client: httpx.AsyncClient,
        authenticated_user_with_company: dict,
    ) -> None:
        """Test updating multiple fields at once."""
        headers = authenticated_user_with_company["headers"]
        user = authenticated_user_with_company["user"]

        payload = {
            "first_name": "NewFirst",
            "last_name": "NewLast",
            "email": "newemail@test.com",
        }
        response = await api_client.patch("/api/v1/users/me", json=payload, headers=headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data["first_name"] == "NewFirst"
        assert data["last_name"] == "NewLast"
        assert data["email"] == "newemail@test.com"

        await user.refresh_from_db()
        assert user.first_name == "NewFirst"
        assert user.last_name == "NewLast"
        assert user.email == "newemail@test.com"

    async def test_update_empty_payload(
        self,
        api_client: httpx.AsyncClient,
        authenticated_user_with_company: dict,
    ) -> None:
        """Test that empty payload doesn't change anything."""
        headers = authenticated_user_with_company["headers"]
        user = authenticated_user_with_company["user"]

        original_first_name = user.first_name
        original_last_name = user.last_name
        original_email = user.email

        payload = {}
        response = await api_client.patch("/api/v1/users/me", json=payload, headers=headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data["first_name"] == original_first_name
        assert data["last_name"] == original_last_name
        assert data["email"] == original_email

        await user.refresh_from_db()
        assert user.first_name == original_first_name
        assert user.last_name == original_last_name
        assert user.email == original_email

    async def test_update_unauthorized(
        self,
        api_client: httpx.AsyncClient,
    ) -> None:
        """Test that updating without authentication fails."""
        payload = {"first_name": "NewName"}
        response = await api_client.patch("/api/v1/users/me", json=payload)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_update_invalid_email(
        self,
        api_client: httpx.AsyncClient,
        authenticated_user_with_company: dict,
    ) -> None:
        """Test that invalid email format is rejected."""
        headers = authenticated_user_with_company["headers"]

        payload = {"email": "not-an-email"}
        response = await api_client.patch("/api/v1/users/me", json=payload, headers=headers)

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    async def test_update_short_password(
        self,
        api_client: httpx.AsyncClient,
        authenticated_user_with_company: dict,
    ) -> None:
        """Test that short password is rejected."""
        headers = authenticated_user_with_company["headers"]

        payload = {"password": "short"}  # pragma: allowlist secret
        response = await api_client.patch("/api/v1/users/me", json=payload, headers=headers)

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    async def test_update_short_first_name(
        self,
        api_client: httpx.AsyncClient,
        authenticated_user_with_company: dict,
    ) -> None:
        """Test that empty first name is rejected."""
        headers = authenticated_user_with_company["headers"]

        payload = {"first_name": ""}
        response = await api_client.patch("/api/v1/users/me", json=payload, headers=headers)

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    async def test_update_preserves_companies(
        self,
        api_client: httpx.AsyncClient,
        authenticated_user_with_company: dict,
    ) -> None:
        """Test that updating user info preserves companies."""
        headers = authenticated_user_with_company["headers"]
        company = authenticated_user_with_company["company"]

        payload = {"first_name": "UpdatedName"}
        response = await api_client.patch("/api/v1/users/me", json=payload, headers=headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert len(data["companies"]) == 1
        assert data["companies"][0]["company_id"] == company.id


class TestGetCurrentUserThreads:
    """Test GET /users/me/threads endpoint."""

    async def test_get_threads_basic(
        self,
        api_client: httpx.AsyncClient,
        authenticated_user_with_company: dict,
    ) -> None:
        """Test /users/me/threads returns assigned threads."""
        from src.backend.modules.orders.models import Order

        headers = authenticated_user_with_company["headers"]
        company = authenticated_user_with_company["company"]
        company_user = authenticated_user_with_company["company_user"]

        customer = await Customer.create(
            user_id="customer_123",
            name="Test Customer",
            company=company,
        )

        order = await Order.create(
            order_number=1,
            customer=customer,
            company=company,
            assignee=company_user,
        )

        await Thread.create(
            thread_id="test_thread_1",
            customer=customer,
            company=company,
            active_order=order,
            channel_type="telegram",
            conversation_id="conv_123",
            state=ThreadState.ACTIVE,
            unread_count=5,
        )

        response = await api_client.get("/api/v1/users/me/threads", headers=headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data["total"] == 1
        assert data["limit"] == 50
        assert data["offset"] == 0
        assert len(data["items"]) == 1

        thread_data = data["items"][0]
        assert thread_data["thread_id"] == "test_thread_1"
        assert thread_data["company_id"] == company.id
        assert thread_data["company_name"] == company.name
        assert thread_data["channel_type"] == "telegram"
        assert thread_data["conversation_id"] == "conv_123"
        assert thread_data["state"] == "active"
        assert thread_data["customer_name"] == "Test Customer"
        assert thread_data["unread_count"] == 5
        assert thread_data["assistant_mode"] == "active"

    async def test_get_threads_pagination(
        self,
        api_client: httpx.AsyncClient,
        authenticated_user_with_company: dict,
    ) -> None:
        """Test /users/me/threads pagination."""
        from src.backend.modules.orders.models import Order

        headers = authenticated_user_with_company["headers"]
        company = authenticated_user_with_company["company"]
        company_user = authenticated_user_with_company["company_user"]

        customer = await Customer.create(
            user_id="customer_123",
            name="Test Customer",
            company=company,
        )

        for i in range(5):
            order = await Order.create(
                order_number=i + 1,
                customer=customer,
                company=company,
                assignee=company_user,
            )
            await Thread.create(
                thread_id=f"thread_{i}",
                customer=customer,
                company=company,
                active_order=order,
                channel_type="telegram",
                state=ThreadState.ACTIVE,
            )

        response = await api_client.get("/api/v1/users/me/threads", headers=headers, params={"limit": 2, "offset": 0})

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data["total"] == 5
        assert data["limit"] == 2
        assert data["offset"] == 0
        assert len(data["items"]) == 2

    async def test_get_threads_empty(
        self,
        api_client: httpx.AsyncClient,
        authenticated_user_with_company: dict,
    ) -> None:
        """Test /users/me/threads with no assigned threads."""
        headers = authenticated_user_with_company["headers"]

        response = await api_client.get("/api/v1/users/me/threads", headers=headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data["total"] == 0
        assert data["limit"] == 50
        assert data["offset"] == 0
        assert len(data["items"]) == 0

    async def test_get_threads_sorted_by_updated_at(
        self,
        api_client: httpx.AsyncClient,
        authenticated_user_with_company: dict,
    ) -> None:
        """Test that threads are sorted by updated_at desc."""
        from datetime import UTC, datetime, timedelta

        from src.backend.modules.orders.models import Order

        headers = authenticated_user_with_company["headers"]
        company = authenticated_user_with_company["company"]
        company_user = authenticated_user_with_company["company_user"]

        customer = await Customer.create(
            user_id="customer_123",
            name="Test Customer",
            company=company,
        )

        now = datetime.now(UTC)
        old_time = now - timedelta(hours=2)

        order1 = await Order.create(
            order_number=1,
            customer=customer,
            company=company,
            assignee=company_user,
        )

        order2 = await Order.create(
            order_number=2,
            customer=customer,
            company=company,
            assignee=company_user,
        )

        await Thread.create(
            thread_id="old_thread",
            customer=customer,
            company=company,
            active_order=order1,
            channel_type="telegram",
            state=ThreadState.ACTIVE,
        )

        await Thread.create(
            thread_id="new_thread",
            customer=customer,
            company=company,
            active_order=order2,
            channel_type="telegram",
            state=ThreadState.ACTIVE,
        )

        await Thread.filter(thread_id="old_thread").update(updated_at=old_time)
        await Thread.filter(thread_id="new_thread").update(updated_at=now)

        response = await api_client.get("/api/v1/users/me/threads", headers=headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert len(data["items"]) == 2
        assert data["items"][0]["thread_id"] == "new_thread"
        assert data["items"][1]["thread_id"] == "old_thread"

    async def test_get_threads_unauthorized(self, api_client: httpx.AsyncClient) -> None:
        """Test /users/me/threads without authentication."""
        response = await api_client.get("/api/v1/users/me/threads")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
