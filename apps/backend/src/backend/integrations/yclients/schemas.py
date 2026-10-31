"""YClients API response and request schemas.

Models mirror the YClients online-booking API documented at
https://developers.yclients.com/ru/ and in plans/031-yclients-integration.md.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

# ------------------------------------------------------------------
# Generic wrapper
# ------------------------------------------------------------------


class YClientsResponse[T](BaseModel):
    success: bool
    data: T
    meta: Any = None


# ------------------------------------------------------------------
# Services & categories
# ------------------------------------------------------------------


class YClientsCategory(BaseModel):
    id: int
    title: str
    sex: int = 0
    weight: int = 0


class YClientsService(BaseModel):
    id: int
    title: str
    category_id: int
    price_min: float = 0
    price_max: float = 0
    discount: float = 0
    comment: str = ""
    weight: int = 0
    active: int = 0
    sex: int = 0
    image: str = ""
    prepaid: str = "forbidden"
    seance_length: int | None = None


class YClientsServicesData(BaseModel):
    category: list[YClientsCategory] = Field(default_factory=list)
    services: list[YClientsService] = Field(default_factory=list)
    events: list[Any] = Field(default_factory=list)


# ------------------------------------------------------------------
# Staff
# ------------------------------------------------------------------


class YClientsStaff(BaseModel):
    id: int
    name: str
    bookable: bool = True
    specialization: str = ""
    show_rating: str | int = ""
    rating: str | int = ""
    votes_count: str | int = ""
    avatar: str = ""
    comments_count: str | int = ""
    weight: str | int = ""
    information: str = ""
    seance_date: str | int | None = None


# ------------------------------------------------------------------
# Dates
# ------------------------------------------------------------------


class YClientsBookingDates(BaseModel):
    booking_days: dict[str, list[str | int]] = Field(default_factory=dict)
    booking_dates: list[str | int] = Field(default_factory=list)
    working_days: dict[str, list[str | int]] = Field(default_factory=dict)
    working_dates: list[str | int] = Field(default_factory=list)


# ------------------------------------------------------------------
# Time slots (seances)
# ------------------------------------------------------------------


class YClientsSeance(BaseModel):
    time: str
    seance_length: int
    datetime: str | int


class YClientsStaffSeances(BaseModel):
    seance_date: str | int | None = None
    seances: list[YClientsSeance] = Field(default_factory=list)


# ------------------------------------------------------------------
# Booking request / response
# ------------------------------------------------------------------


class YClientsAppointment(BaseModel):
    id: int = 1
    services: list[int]
    staff_id: int
    datetime: str | int
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class YClientsBookingRequest(BaseModel):
    phone: str
    fullname: str
    email: str = ""
    comment: str = ""
    notify_by_sms: int | None = None
    notify_by_email: int | None = None
    api_id: str = ""
    custom_fields: dict[str, Any] = Field(default_factory=dict)
    appointments: list[YClientsAppointment]


class YClientsBookingResult(BaseModel):
    id: int
    record_id: int
    record_hash: str


class YClientsRescheduleRequest(BaseModel):
    datetime: str | int
    comment: str = ""


# ------------------------------------------------------------------
# Check booking
# ------------------------------------------------------------------


class YClientsCheckAppointment(BaseModel):
    id: int = 1
    services: list[int]
    staff_id: int
    datetime: str | int


class YClientsCheckRequest(BaseModel):
    appointments: list[YClientsCheckAppointment]
