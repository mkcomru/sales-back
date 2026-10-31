"""Tests for UsersService."""

from __future__ import annotations

import pytest
from passlib.context import CryptContext

from common.models.pagination import PaginatedResponse

from src.backend.modules.chat.models import Thread, ThreadState
from src.backend.modules.users.exceptions import UserAlreadyExistsError
from src.backend.modules.users.models import CompanyUser, UserRole
from src.backend.modules.users.schemas import UserDetailResponse
from src.backend.modules.users.service import UsersService

pytestmark = pytest.mark.asyncio


class TestPasswordHashing:
    """Test password hashing functionality."""

    async def test_get_password_hash(self, users_service: UsersService) -> None:
        password = "test_password_123"  # pragma: allowlist secret
        hashed = users_service.get_password_hash(password)

        assert hashed != password
        assert len(hashed) > 0

        pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        assert pwd_context.verify(password, hashed)


class TestCreateUser:
    """Test user creation."""

    async def test_create_user_basic(self, users_service: UsersService) -> None:
        user = await users_service.create_user(
            first_name="John",
            last_name="Doe",
            email="test@example.com",
            password="test_password_123",  # pragma: allowlist secret
            is_superuser=False,
        )

        assert user.id is not None
        assert user.first_name == "John"
        assert user.last_name == "Doe"
        assert user.email == "test@example.com"
        assert user.is_active is True
        assert user.is_superuser is False
        assert user.hashed_password != "test_password_123"  # pragma: allowlist secret

    async def test_create_user_email_lowercase(self, users_service: UsersService) -> None:
        user = await users_service.create_user(
            first_name="JOHN",
            last_name="DOE",
            email="TEST@EXAMPLE.COM",
            password="test_password_123",  # pragma: allowlist secret
            is_superuser=False,
        )

        assert user.first_name == "JOHN"
        assert user.last_name == "DOE"
        assert user.email == "test@example.com"

    async def test_create_superuser(self, users_service: UsersService) -> None:
        user = await users_service.create_user(
            first_name="Admin",
            last_name="User",
            email="admin@example.com",
            password="admin_password_123",  # pragma: allowlist secret
            is_superuser=True,
        )

        assert user.first_name == "Admin"
        assert user.last_name == "User"
        assert user.is_superuser is True

    async def test_create_user_duplicate_email(self, users_service: UsersService) -> None:
        await users_service.create_user(
            first_name="Test",
            last_name="User",
            email="test@example.com",
            password="test_password_123",  # pragma: allowlist secret
        )

        with pytest.raises(UserAlreadyExistsError):
            await users_service.create_user(
                first_name="Test",
                last_name="User",
                email="test@example.com",
                password="another_password",  # pragma: allowlist secret
            )

    async def test_create_user_duplicate_email_case_insensitive(
        self,
        users_service: UsersService,
    ) -> None:
        await users_service.create_user(
            first_name="Test",
            last_name="User",
            email="test@example.com",
            password="test_password_123",  # pragma: allowlist secret
        )

        with pytest.raises(UserAlreadyExistsError):
            await users_service.create_user(
                first_name="Test",
                last_name="User",
                email="TEST@EXAMPLE.COM",
                password="another_password",  # pragma: allowlist secret
            )


class TestGetUserDetail:
    """Test get_user_detail method."""

    async def test_get_user_detail_basic(
        self,
        users_service: UsersService,
        company_factory,
    ) -> None:
        user = await users_service.create_user(
            first_name="Test",
            last_name="User",
            email="test@example.com",
            password="test_password_123",  # pragma: allowlist secret
        )

        result = await users_service.get_user_detail(user)

        assert isinstance(result, UserDetailResponse)
        assert result.id == user.id
        assert result.first_name == "Test"
        assert result.last_name == "User"
        assert result.email == "test@example.com"
        assert result.is_active is True
        assert result.is_superuser is False
        assert len(result.companies) == 0

    async def test_get_user_detail_with_companies(
        self,
        users_service: UsersService,
        company_factory,
    ) -> None:
        user = await users_service.create_user(
            first_name="Test",
            last_name="User",
            email="test@example.com",
            password="test_password_123",  # pragma: allowlist secret
        )

        company1 = await company_factory(name="Company 1")
        company2 = await company_factory(name="Company 2")

        await CompanyUser.create(
            user=user,
            company=company1,
            role=UserRole.ADMIN,
        )
        await CompanyUser.create(
            user=user,
            company=company2,
            role=UserRole.VIEWER,
        )

        result = await users_service.get_user_detail(user)

        assert len(result.companies) == 2
        company_ids = {c.company_id for c in result.companies}
        assert company1.id in company_ids
        assert company2.id in company_ids

        admin_company = next(c for c in result.companies if c.company_id == company1.id)
        assert admin_company.role == "admin"
        assert admin_company.company_name == "Company 1"


class TestGetUserThreads:
    """Test get_user_threads method."""

    async def test_get_user_threads_basic(
        self,
        users_service: UsersService,
        company_factory,
    ) -> None:
        from src.backend.modules.chat.models import Customer
        from src.backend.modules.orders.models import Order

        user = await users_service.create_user(
            first_name="Test",
            last_name="User",
            email="test@example.com",
            password="test_password_123",  # pragma: allowlist secret
        )

        company = await company_factory(name="Test Company")
        company_user = await CompanyUser.create(
            user=user,
            company=company,
            role=UserRole.MANAGER,
        )

        customer = await Customer.create(
            user_id="customer_123",
            name="John Doe",
            company=company,
        )

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
            thread_id="thread_1",
            customer=customer,
            company=company,
            active_order=order1,
            channel_type="telegram",
            conversation_id="conv_1",
            state=ThreadState.ACTIVE,
        )

        await Thread.create(
            thread_id="thread_2",
            customer=customer,
            company=company,
            active_order=order2,
            channel_type="whatsapp",
            conversation_id="conv_2",
            state=ThreadState.WAITING_MANAGER,
        )

        result = await users_service.get_user_threads(user)

        assert isinstance(result, PaginatedResponse)
        assert result.total == 2
        assert result.limit == 50
        assert result.offset == 0
        assert len(result.items) == 2

        thread_ids = {t.thread_id for t in result.items}
        assert "thread_1" in thread_ids
        assert "thread_2" in thread_ids

        thread1_info = next(t for t in result.items if t.thread_id == "thread_1")
        assert thread1_info.channel_type == "telegram"
        assert thread1_info.state == "active"
        assert thread1_info.customer_name == "John Doe"
        assert thread1_info.company_name == "Test Company"

    async def test_get_user_threads_pagination(
        self,
        users_service: UsersService,
        company_factory,
    ) -> None:
        from src.backend.modules.chat.models import Customer
        from src.backend.modules.orders.models import Order

        user = await users_service.create_user(
            first_name="Test",
            last_name="User",
            email="test@example.com",
            password="test_password_123",  # pragma: allowlist secret
        )

        company = await company_factory(name="Test Company")
        company_user = await CompanyUser.create(
            user=user,
            company=company,
            role=UserRole.MANAGER,
        )

        customer = await Customer.create(
            user_id="customer_123",
            name="John Doe",
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

        result = await users_service.get_user_threads(user, limit=2, offset=0)

        assert result.total == 5
        assert result.limit == 2
        assert result.offset == 0
        assert len(result.items) == 2

    async def test_get_user_threads_empty(
        self,
        users_service: UsersService,
        company_factory,
    ) -> None:
        user = await users_service.create_user(
            first_name="Test",
            last_name="User",
            email="test@example.com",
            password="test_password_123",  # pragma: allowlist secret
        )

        result = await users_service.get_user_threads(user)

        assert result.total == 0
        assert result.limit == 50
        assert result.offset == 0
        assert len(result.items) == 0

    async def test_get_user_threads_ordered_by_updated_at(
        self,
        users_service: UsersService,
        company_factory,
    ) -> None:
        from datetime import UTC, datetime, timedelta

        from src.backend.modules.chat.models import Customer
        from src.backend.modules.orders.models import Order

        user = await users_service.create_user(
            first_name="Test",
            last_name="User",
            email="test@example.com",
            password="test_password_123",  # pragma: allowlist secret
        )

        company = await company_factory(name="Test Company")
        company_user = await CompanyUser.create(
            user=user,
            company=company,
            role=UserRole.MANAGER,
        )

        customer = await Customer.create(
            user_id="customer_123",
            name="John Doe",
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

        result = await users_service.get_user_threads(user)

        assert len(result.items) == 2
        assert result.items[0].thread_id == "new_thread"
        assert result.items[1].thread_id == "old_thread"

    async def test_get_user_threads_multiple_companies(
        self,
        users_service: UsersService,
        company_factory,
    ) -> None:
        from src.backend.modules.chat.models import Customer
        from src.backend.modules.orders.models import Order

        user = await users_service.create_user(
            first_name="Test",
            last_name="User",
            email="test@example.com",
            password="test_password_123",  # pragma: allowlist secret
        )

        company1 = await company_factory(name="Company 1")
        company2 = await company_factory(name="Company 2")

        company_user1 = await CompanyUser.create(
            user=user,
            company=company1,
            role=UserRole.ADMIN,
        )
        company_user2 = await CompanyUser.create(
            user=user,
            company=company2,
            role=UserRole.MANAGER,
        )

        customer1 = await Customer.create(
            user_id="customer_1",
            name="Customer 1",
            company=company1,
        )
        customer2 = await Customer.create(
            user_id="customer_2",
            name="Customer 2",
            company=company2,
        )

        order1 = await Order.create(
            order_number=1,
            customer=customer1,
            company=company1,
            assignee=company_user1,
        )

        order2 = await Order.create(
            order_number=1,
            customer=customer2,
            company=company2,
            assignee=company_user2,
        )

        await Thread.create(
            thread_id="thread_c1",
            customer=customer1,
            company=company1,
            active_order=order1,
            channel_type="telegram",
            state=ThreadState.ACTIVE,
        )

        await Thread.create(
            thread_id="thread_c2",
            customer=customer2,
            company=company2,
            active_order=order2,
            channel_type="whatsapp",
            state=ThreadState.ACTIVE,
        )

        result = await users_service.get_user_threads(user)

        assert result.total == 2
        thread_company_names = {t.company_name for t in result.items}
        assert "Company 1" in thread_company_names
        assert "Company 2" in thread_company_names
