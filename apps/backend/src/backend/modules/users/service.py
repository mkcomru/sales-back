from __future__ import annotations

from zoneinfo import ZoneInfo

import structlog
from passlib.context import CryptContext

from common.models.pagination import PaginatedResponse

from src.backend.modules.chat.models import Thread
from src.backend.modules.orders.models import Order
from src.backend.modules.users.exceptions import UserAlreadyExistsError
from src.backend.modules.users.models import CompanyUser, User
from src.backend.modules.users.schedule_service import schedule_service
from src.backend.modules.users.schemas import (
    AvailableManagerInfo,
    CompanyUserScheduleResponse,
    UserCompanyInfo,
    UserDetailResponse,
    UserThreadInfo,
)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
log = structlog.get_logger(__name__)


class UsersService:
    def __init__(self, users_repository):
        self.users_repository = users_repository

    @staticmethod
    def get_password_hash(password: str) -> str:
        return pwd_context.hash(password)

    async def create_user(
        self,
        first_name: str,
        last_name: str,
        email: str,
        password: str,
        is_superuser: bool = False,
    ) -> User:
        existing = await User.filter(email=email.lower()).first()
        if existing:
            log.warning("users.create_user.email_exists", email=email)
            raise UserAlreadyExistsError(f"User with email {email} already exists")

        hashed_password = self.get_password_hash(password)
        user = await User.create(
            first_name=first_name,
            last_name=last_name,
            email=email.lower(),
            hashed_password=hashed_password,
            is_active=True,
            is_superuser=is_superuser,
        )
        return user

    async def get_user_detail(self, user: User) -> UserDetailResponse:
        company_users = await CompanyUser.filter(user_id=user.id).prefetch_related("company")

        companies = [
            UserCompanyInfo(
                id=cu.id,
                company_id=cu.company.id,
                company_name=cu.company.name,
                role=cu.role.value,
            )
            for cu in company_users
        ]

        return UserDetailResponse(
            id=user.id,
            first_name=user.first_name,
            last_name=user.last_name,
            email=user.email,
            is_active=user.is_active,
            is_superuser=user.is_superuser,
            created_at=user.created_at.isoformat(),
            updated_at=user.updated_at.isoformat(),
            companies=companies,
        )

    async def get_user_threads(
        self,
        user: User,
        limit: int = 50,
        offset: int = 0,
    ) -> PaginatedResponse[UserThreadInfo]:
        company_users = await CompanyUser.filter(user_id=user.id).all()
        company_user_ids = [cu.id for cu in company_users]

        if not company_user_ids:
            return PaginatedResponse(items=[], total=0, limit=limit, offset=offset)

        assigned_orders = await Order.filter(assignee_id__in=company_user_ids).all()
        order_ids = [order.id for order in assigned_orders]

        if not order_ids:
            return PaginatedResponse(items=[], total=0, limit=limit, offset=offset)

        total = await Thread.filter(active_order_id__in=order_ids).count()

        threads = (
            await Thread.filter(active_order_id__in=order_ids)
            .prefetch_related("company", "customer")
            .order_by("-updated_at")
            .offset(offset)
            .limit(limit)
        )

        items = [
            UserThreadInfo(
                thread_id=thread.thread_id,
                company_id=thread.company.id,
                company_name=thread.company.name,
                channel_type=thread.channel_type,
                conversation_id=thread.conversation_id,
                state=thread.state.value,
                customer_name=thread.customer.name,
                unread_count=thread.unread_count,
                assistant_mode=thread.assistant_mode.value,
                created_at=thread.created_at,
                updated_at=thread.updated_at,
            )
            for thread in threads
        ]

        return PaginatedResponse(items=items, total=total, limit=limit, offset=offset)

    async def update_user(
        self,
        user: User,
        first_name: str | None,
        last_name: str | None,
        email: str | None,
        password: str | None,
    ) -> UserDetailResponse:
        hashed_password = self.get_password_hash(password) if password is not None else None

        if email is not None:
            existing = await User.filter(email=email.lower()).exclude(id=user.id).first()
            if existing:
                log.warning("users.update_user.email_exists", email=email, user_id=user.id)
                raise UserAlreadyExistsError(f"User with email {email} already exists")

        updated_user = await self.users_repository.update_user(user.id, first_name, last_name, email, hashed_password)
        return await self.get_user_detail(updated_user)

    async def update_company_user(
        self,
        company_user: CompanyUser,
        work_schedule: dict | None = None,
        is_available: bool | None = None,
    ) -> CompanyUser:
        """Update company user work schedule and availability."""
        update_fields = []
        if work_schedule is not None:
            company_user.work_schedule = work_schedule
            update_fields.append("work_schedule")
        if is_available is not None:
            company_user.is_available = is_available
            update_fields.append("is_available")

        if update_fields:
            await company_user.save(update_fields=update_fields)

        return company_user

    async def get_company_user_schedule(self, company_user: CompanyUser) -> CompanyUserScheduleResponse:
        """Get company user schedule with interpretation."""
        await company_user.fetch_related("user")

        schedule_info = schedule_service.get_manager_schedule_info(company_user)

        next_available_at_local = None
        timezone_str = None

        if schedule_info.schedule and schedule_info.next_working_time:
            timezone_str = schedule_info.schedule.timezone
            tz = ZoneInfo(timezone_str)
            local_time = schedule_info.next_working_time.astimezone(tz)
            next_available_at_local = local_time.strftime("%Y-%m-%d %H:%M")

        work_schedule = None
        if schedule_info.schedule:
            from src.backend.modules.users.schemas import WorkSchedule

            work_schedule = WorkSchedule.model_validate(company_user.work_schedule)

        return CompanyUserScheduleResponse(
            work_schedule=work_schedule,
            is_available=company_user.is_available,
            schedule_description=schedule_info.schedule_description,
            is_working_now=schedule_info.is_working,
            next_available_at=schedule_info.next_working_time,
            next_available_at_local=next_available_at_local,
            next_available_timezone=timezone_str,
        )

    async def get_available_managers(self, company_id: int) -> list[AvailableManagerInfo]:
        """Get list of available managers for a company."""
        from src.backend.modules.companies.models import Company

        company = await Company.get_or_none(id=company_id)
        if not company:
            return []

        managers = await schedule_service.get_available_managers(company)

        result = []
        for manager in managers:
            await manager.fetch_related("user")

            schedule_info = schedule_service.get_manager_schedule_info(manager)

            next_available_at_local = None
            if schedule_info.next_working_time and schedule_info.schedule:
                tz = ZoneInfo(schedule_info.schedule.timezone)
                local_time = schedule_info.next_working_time.astimezone(tz)
                next_available_at_local = local_time.strftime("%Y-%m-%d %H:%M")

            manager_name = manager.get_full_name()

            result.append(
                AvailableManagerInfo(
                    id=manager.id,
                    user_id=manager.user.id,
                    name=manager_name,
                    email=manager.user.email,
                    role=manager.role.value,
                    is_available=manager.is_available,
                    is_working_now=schedule_info.is_working,
                    schedule_description=schedule_info.schedule_description,
                    next_available_at=schedule_info.next_working_time,
                    next_available_at_local=next_available_at_local,
                    last_assigned_at=manager.last_assigned_at,
                )
            )

        return result
