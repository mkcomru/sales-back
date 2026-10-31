"""Provider-agnostic request/response schemas for capability endpoints.

These are what the sales-agent sees — no provider-specific details leak out.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

# ------------------------------------------------------------------
# Scheduling: services
# ------------------------------------------------------------------


class ServiceItem(BaseModel):
    id: int
    title: str
    category: str = ""
    price_min: float = 0
    price_max: float = 0
    duration_seconds: int | None = None


class GetServicesRequest(BaseModel):
    company_id: int
    staff_id: int | None = None


class GetServicesResponse(BaseModel):
    services: list[ServiceItem]


# ------------------------------------------------------------------
# Scheduling: staff
# ------------------------------------------------------------------


class StaffItem(BaseModel):
    id: int
    name: str
    specialization: str = ""
    bookable: bool = True
    rating: str | int = ""
    avatar: str = ""


class GetStaffRequest(BaseModel):
    company_id: int
    service_ids: list[int] = Field(default_factory=list)


class GetStaffResponse(BaseModel):
    staff: list[StaffItem]


# ------------------------------------------------------------------
# Scheduling: available dates
# ------------------------------------------------------------------


class GetDatesRequest(BaseModel):
    company_id: int
    staff_id: int
    service_ids: list[int] = Field(default_factory=list)


class GetDatesResponse(BaseModel):
    dates: list[str] = Field(default_factory=list)


# ------------------------------------------------------------------
# Scheduling: available slots
# ------------------------------------------------------------------


class TimeSlot(BaseModel):
    time: str
    duration_seconds: int
    datetime_ts: str | int


class GetSlotsRequest(BaseModel):
    company_id: int
    staff_id: int
    date: str = Field(description="YYYY-MM-DD")
    service_ids: list[int] = Field(default_factory=list)


class GetSlotsResponse(BaseModel):
    slots: list[TimeSlot]


# ------------------------------------------------------------------
# Scheduling: create booking
# ------------------------------------------------------------------


class BookingAppointment(BaseModel):
    service_ids: list[int]
    staff_id: int
    datetime: str | int


class CreateBookingRequest(BaseModel):
    company_id: int
    phone: str
    fullname: str
    email: str = ""
    comment: str = ""
    appointments: list[BookingAppointment]


class BookingResultItem(BaseModel):
    record_id: int
    record_hash: str


class CreateBookingResponse(BaseModel):
    bookings: list[BookingResultItem]
