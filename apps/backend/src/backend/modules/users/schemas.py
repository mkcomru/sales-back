from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator


class CreateUserRequest(BaseModel):
    first_name: str = Field(min_length=1, max_length=255)
    last_name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    password: str = Field(min_length=8)
    is_superuser: bool = False


class UserResponse(BaseModel):
    id: int
    first_name: str
    last_name: str
    email: str
    is_active: bool
    is_superuser: bool
    created_at: str


class UserCompanyInfo(BaseModel):
    id: int = Field(description="CompanyUser ID for this company membership")
    company_id: int
    company_name: str
    role: str


class UserThreadInfo(BaseModel):
    thread_id: str
    company_id: int
    company_name: str
    channel_type: str
    conversation_id: str | None
    state: str
    customer_name: str | None
    unread_count: int
    assistant_mode: str
    created_at: datetime
    updated_at: datetime


class UpdateUserRequest(BaseModel):
    first_name: str | None = Field(None, min_length=1, max_length=255)
    last_name: str | None = Field(None, min_length=1, max_length=255)
    email: EmailStr | None = None
    password: str | None = Field(None, min_length=8)


class UserDetailResponse(BaseModel):
    id: int
    first_name: str
    last_name: str
    email: str
    is_active: bool
    is_superuser: bool
    created_at: str
    updated_at: str
    companies: list[UserCompanyInfo]


class TimeSlot(BaseModel):
    start: str = Field(pattern=r"^([01]\d|2[0-3]):([0-5]\d)$")
    end: str = Field(pattern=r"^([01]\d|2[0-3]):([0-5]\d)$")

    @model_validator(mode="after")
    def validate_time_order(self) -> "TimeSlot":
        start_hour, start_minute = map(int, self.start.split(":"))
        end_hour, end_minute = map(int, self.end.split(":"))
        start_total = start_hour * 60 + start_minute
        end_total = end_hour * 60 + end_minute
        if start_total >= end_total:
            raise ValueError("start must be less than end")
        return self


class WeeklySchedule(BaseModel):
    mon: list[TimeSlot]
    tue: list[TimeSlot]
    wed: list[TimeSlot]
    thu: list[TimeSlot]
    fri: list[TimeSlot]
    sat: list[TimeSlot]
    sun: list[TimeSlot]

    @model_validator(mode="after")
    def validate_single_slot_per_day(self) -> "WeeklySchedule":
        for day_name, slots in [
            ("mon", self.mon),
            ("tue", self.tue),
            ("wed", self.wed),
            ("thu", self.thu),
            ("fri", self.fri),
            ("sat", self.sat),
            ("sun", self.sun),
        ]:
            if len(slots) > 1:
                raise ValueError(f"{day_name} must have at most one slot in MVP")
        return self


class WorkSchedule(BaseModel):
    version: int = Field(ge=1)
    timezone: str
    weekly: WeeklySchedule

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, v: str) -> str:
        try:
            ZoneInfo(v)
        except ZoneInfoNotFoundError:
            raise ValueError(f"Invalid IANA timezone: {v}") from None
        return v


class UpdateCompanyUserRequest(BaseModel):
    work_schedule: WorkSchedule | None = None
    is_available: bool | None = None


class UpdateCompanyUserResponse(BaseModel):
    id: int
    work_schedule: dict | None
    is_available: bool


class CompanyUserScheduleResponse(BaseModel):
    work_schedule: WorkSchedule | None
    is_available: bool
    schedule_description: str | None
    is_working_now: bool
    next_available_at: datetime | None
    next_available_at_local: str | None
    next_available_timezone: str | None


class ManagerScheduleInfo(BaseModel):
    schedule: WorkSchedule | None
    is_working: bool
    next_working_time: datetime | None
    schedule_description: str | None


class AvailableManagerInfo(BaseModel):
    id: int
    user_id: int
    name: str
    email: str
    role: str
    is_available: bool
    is_working_now: bool
    schedule_description: str | None
    next_available_at: datetime | None
    next_available_at_local: str | None
    last_assigned_at: datetime | None
