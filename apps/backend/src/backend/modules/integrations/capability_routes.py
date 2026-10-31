"""Internal capability action endpoints (service-key auth).

Each endpoint resolves the company's integration for a given capability,
builds a provider client, and proxies the call. The sales-agent calls these
endpoints — it never talks to external APIs directly.
"""

from __future__ import annotations

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, status

from common.integrations import Capability

from src.backend.integrations.yclients.client import YClientsClient, YClientsError
from src.backend.integrations.yclients.schemas import YClientsCheckAppointment, YClientsCheckRequest
from src.backend.modules.core.dependencies import require_service_api_key
from src.backend.modules.integrations.capability_schemas import (
    BookingResultItem,
    CreateBookingRequest,
    CreateBookingResponse,
    GetDatesRequest,
    GetDatesResponse,
    GetServicesRequest,
    GetServicesResponse,
    GetSlotsRequest,
    GetSlotsResponse,
    GetStaffRequest,
    GetStaffResponse,
    ServiceItem,
    StaffItem,
    TimeSlot,
)
from src.backend.modules.integrations.dependencies import IntegrationServiceDep

log = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/internal/capabilities",
    tags=["capabilities:internal"],
    dependencies=[Depends(require_service_api_key)],
)


def _raise_booking_error(exc: YClientsError) -> None:
    status_code = exc.status_code if exc.status_code >= 400 else status.HTTP_409_CONFLICT
    raise HTTPException(status_code=status_code, detail=exc.message or "Booking request was rejected") from exc


# ------------------------------------------------------------------
# Scheduling: services
# ------------------------------------------------------------------


@router.post("/scheduling/services", response_model=GetServicesResponse)
async def get_booking_services(
    request: GetServicesRequest,
    service: IntegrationServiceDep,
) -> GetServicesResponse:
    integration = await service.resolve_by_capability(request.company_id, Capability.SCHEDULING)
    async with service.build_client(integration) as client:
        assert isinstance(client, YClientsClient)
        data = await client.get_services(staff_id=request.staff_id)
        categories_map = {c.id: c.title for c in data.category}
        return GetServicesResponse(
            services=[
                ServiceItem(
                    id=s.id,
                    title=s.title,
                    category=categories_map.get(s.category_id, ""),
                    price_min=s.price_min,
                    price_max=s.price_max,
                    duration_seconds=s.seance_length,
                )
                for s in data.services
            ]
        )


# ------------------------------------------------------------------
# Scheduling: staff
# ------------------------------------------------------------------


@router.post("/scheduling/staff", response_model=GetStaffResponse)
async def get_staff(
    request: GetStaffRequest,
    service: IntegrationServiceDep,
) -> GetStaffResponse:
    integration = await service.resolve_by_capability(request.company_id, Capability.STAFF)
    async with service.build_client(integration) as client:
        assert isinstance(client, YClientsClient)
        staff_list = await client.get_staff(
            service_ids=request.service_ids or None,
        )
        return GetStaffResponse(
            staff=[
                StaffItem(
                    id=s.id,
                    name=s.name,
                    specialization=s.specialization,
                    bookable=s.bookable,
                    rating=s.rating,
                    avatar=s.avatar,
                )
                for s in staff_list
            ]
        )


# ------------------------------------------------------------------
# Scheduling: available dates
# ------------------------------------------------------------------


@router.post("/scheduling/dates", response_model=GetDatesResponse)
async def get_available_dates(
    request: GetDatesRequest,
    service: IntegrationServiceDep,
) -> GetDatesResponse:
    integration = await service.resolve_by_capability(request.company_id, Capability.SCHEDULING)
    async with service.build_client(integration) as client:
        assert isinstance(client, YClientsClient)
        data = await client.get_available_dates(
            staff_id=request.staff_id,
            service_ids=request.service_ids or None,
        )
        return GetDatesResponse(dates=[str(date) for date in data.booking_dates])


# ------------------------------------------------------------------
# Scheduling: available slots
# ------------------------------------------------------------------


@router.post("/scheduling/slots", response_model=GetSlotsResponse)
async def get_available_slots(
    request: GetSlotsRequest,
    service: IntegrationServiceDep,
) -> GetSlotsResponse:
    integration = await service.resolve_by_capability(request.company_id, Capability.SCHEDULING)
    async with service.build_client(integration) as client:
        assert isinstance(client, YClientsClient)
        seances = await client.get_available_slots(
            staff_id=request.staff_id,
            date=request.date,
            service_ids=request.service_ids or None,
        )
        return GetSlotsResponse(
            slots=[
                TimeSlot(
                    time=s.time,
                    duration_seconds=s.seance_length,
                    datetime_ts=s.datetime,
                )
                for s in seances
            ]
        )


# ------------------------------------------------------------------
# Scheduling: create booking
# ------------------------------------------------------------------


@router.post("/scheduling/bookings", response_model=CreateBookingResponse)
async def create_booking(
    request: CreateBookingRequest,
    service: IntegrationServiceDep,
) -> CreateBookingResponse:
    integration = await service.resolve_by_capability(request.company_id, Capability.SCHEDULING)
    async with service.build_client(integration) as client:
        assert isinstance(client, YClientsClient)
        appointments = [
            {"service_ids": a.service_ids, "staff_id": a.staff_id, "datetime": a.datetime} for a in request.appointments
        ]
        # AICODE-NOTE: book_check is best-effort — infrastructure errors (401, timeout) are logged
        # and we proceed with booking. Business errors (slot taken) are raised to the agent.
        check_request = YClientsCheckRequest(
            appointments=[
                YClientsCheckAppointment(
                    id=index,
                    services=a["service_ids"],
                    staff_id=a["staff_id"],
                    datetime=a["datetime"],
                )
                for index, a in enumerate(appointments, start=1)
            ]
        )
        try:
            await client.check_booking(check_request)
        except YClientsError as exc:
            _raise_booking_error(exc)
        except httpx.HTTPStatusError:
            log.warning(
                "booking.check_skipped",
                company_id=request.company_id,
                reason="provider returned HTTP error on book_check, proceeding with booking",
            )
        try:
            results = await client.create_booking(
                phone=request.phone,
                fullname=request.fullname,
                email=request.email,
                comment=request.comment,
                appointments=appointments,
            )
        except YClientsError as exc:
            _raise_booking_error(exc)
        except httpx.HTTPStatusError as exc:
            raise HTTPException(
                status_code=exc.response.status_code,
                detail=f"Booking provider error: {exc.response.status_code}",
            ) from exc
        return CreateBookingResponse(
            bookings=[BookingResultItem(record_id=r.record_id, record_hash=r.record_hash) for r in results]
        )
