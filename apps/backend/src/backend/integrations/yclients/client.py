"""YClients HTTP client — online booking API.

Wraps the YClients booking endpoints documented at
https://developers.yclients.com/ru/.
All methods correspond to the "Онлайн-запись" section of the API.
"""

from __future__ import annotations

import httpx
import structlog

from src.backend.integrations.base import BaseIntegrationClient
from src.backend.integrations.yclients.config import (
    YCLIENTS_BASE_URL,
    YCLIENTS_RATE_LIMIT_RPS,
    YClientsConfig,
    YClientsCredentials,
)
from src.backend.integrations.yclients.schemas import (
    YClientsAppointment,
    YClientsBookingDates,
    YClientsBookingRequest,
    YClientsBookingResult,
    YClientsCheckRequest,
    YClientsRescheduleRequest,
    YClientsSeance,
    YClientsServicesData,
    YClientsStaff,
    YClientsStaffSeances,
)

log = structlog.get_logger(__name__)

YCLIENTS_ACCEPT_HEADER = "application/vnd.yclients.v2+json"


class YClientsError(Exception):
    """Non-retryable error from YClients API."""

    def __init__(self, status_code: int, code: int | None, message: str) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(f"YClients {status_code} (code={code}): {message}")


class YClientsClient(BaseIntegrationClient):
    provider_type: str = "yclients"

    def __init__(self, credentials: YClientsCredentials, config: YClientsConfig) -> None:
        self._credentials = credentials
        self._config = config
        super().__init__(
            base_url=YCLIENTS_BASE_URL,
            headers={
                "Authorization": f"Bearer {credentials.partner_token}",
                "Accept": YCLIENTS_ACCEPT_HEADER,
                "Content-Type": "application/json",
            },
            rate_limit_rps=YCLIENTS_RATE_LIMIT_RPS,
        )

    @property
    def company_id(self) -> int:
        return self._config.yclients_company_id

    # ------------------------------------------------------------------
    # Response handling
    # ------------------------------------------------------------------

    async def request(self, method: str, path: str, **kwargs: object) -> httpx.Response:
        try:
            return await super().request(method, path, **kwargs)
        except httpx.HTTPStatusError as exc:
            self._raise_from_body(exc)
            raise

    def _raise_from_body(self, exc: httpx.HTTPStatusError) -> None:
        """Try to extract a YClients error message from an HTTP error response body."""
        try:
            body = exc.response.json()
        except Exception:
            return
        meta = body.get("meta") or {}
        message = meta.get("message", "") if isinstance(meta, dict) else str(meta)
        if message:
            raise YClientsError(
                status_code=exc.response.status_code,
                code=meta.get("code") if isinstance(meta, dict) else None,
                message=message,
            ) from exc

    def _parse_response(self, response: httpx.Response) -> dict:
        body = response.json()
        if not body.get("success", True):
            meta = body.get("meta") or {}
            message = meta.get("message", "") if isinstance(meta, dict) else str(meta)
            raise YClientsError(
                status_code=response.status_code,
                code=meta.get("code") if isinstance(meta, dict) else None,
                message=message,
            )
        return body.get("data")

    # ------------------------------------------------------------------
    # 1. Services
    # ------------------------------------------------------------------

    async def get_services(
        self,
        *,
        staff_id: int | None = None,
        datetime_filter: str | None = None,
        service_ids: list[int] | None = None,
    ) -> YClientsServicesData:
        params: dict = {}
        if staff_id is not None:
            params["staff_id"] = staff_id
        if datetime_filter:
            params["datetime"] = datetime_filter
        if service_ids:
            params["service_ids[]"] = service_ids

        resp = await self.get(f"/api/v1/book_services/{self.company_id}", params=params)
        return YClientsServicesData.model_validate(self._parse_response(resp))

    # ------------------------------------------------------------------
    # 2. Staff
    # ------------------------------------------------------------------

    async def get_staff(
        self,
        *,
        service_ids: list[int] | None = None,
        datetime_filter: str | None = None,
    ) -> list[YClientsStaff]:
        params: dict = {}
        if service_ids:
            params["service_ids[]"] = service_ids
        if datetime_filter:
            params["datetime"] = datetime_filter

        resp = await self.get(f"/api/v1/book_staff/{self.company_id}", params=params)
        data = self._parse_response(resp)
        return [YClientsStaff.model_validate(s) for s in data]

    # ------------------------------------------------------------------
    # 3. Available dates
    # ------------------------------------------------------------------

    async def get_available_dates(
        self,
        *,
        staff_id: int = 0,
        service_ids: list[int] | None = None,
        date: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> YClientsBookingDates:
        params: dict = {"staff_id": staff_id}
        if service_ids:
            params["service_ids[]"] = service_ids
        if date_from and date_to:
            params["date_from"] = date_from
            params["date_to"] = date_to
        elif date:
            params["date"] = date

        resp = await self.get(f"/api/v1/book_dates/{self.company_id}", params=params)
        return YClientsBookingDates.model_validate(self._parse_response(resp))

    # ------------------------------------------------------------------
    # 4. Available time slots
    # ------------------------------------------------------------------

    async def get_available_slots(
        self,
        *,
        staff_id: int,
        date: str,
        service_ids: list[int] | None = None,
    ) -> list[YClientsSeance]:
        params: dict = {}
        if service_ids:
            params["service_ids[]"] = service_ids

        resp = await self.get(
            f"/api/v1/book_times/{self.company_id}/{staff_id}/{date}",
            params=params,
        )
        data = self._parse_response(resp)
        return [YClientsSeance.model_validate(s) for s in data]

    # ------------------------------------------------------------------
    # 5. Staff nearest seances
    # ------------------------------------------------------------------

    async def get_staff_seances(
        self,
        *,
        staff_id: int,
        service_ids: list[int] | None = None,
    ) -> YClientsStaffSeances:
        params: dict = {}
        if service_ids:
            params["service_ids[]"] = service_ids

        resp = await self.get(
            f"/api/v1/book_staff_seances/{self.company_id}/{staff_id}/",
            params=params,
        )
        return YClientsStaffSeances.model_validate(self._parse_response(resp))

    # ------------------------------------------------------------------
    # 6. Check booking
    # ------------------------------------------------------------------

    async def check_booking(self, request: YClientsCheckRequest) -> None:
        resp = await self.post(
            f"/api/v1/book_check/{self.company_id}",
            content=request.model_dump_json(),
        )
        self._parse_response(resp)

    # ------------------------------------------------------------------
    # 7. Create booking
    # ------------------------------------------------------------------

    async def create_booking(
        self,
        *,
        phone: str,
        fullname: str,
        email: str = "",
        comment: str = "",
        appointments: list[dict],
    ) -> list[YClientsBookingResult]:
        """Create a booking.

        Each appointment dict must have: service_ids (list[int]), staff_id (int), datetime (str|int).
        """
        request = YClientsBookingRequest(
            phone=phone,
            fullname=fullname,
            email=email,
            comment=comment,
            appointments=[
                YClientsAppointment(
                    id=idx + 1,
                    services=a["service_ids"],
                    staff_id=a["staff_id"],
                    datetime=a["datetime"],
                )
                for idx, a in enumerate(appointments)
            ],
        )
        resp = await self.post(
            f"/api/v1/book_record/{self.company_id}",
            content=request.model_dump_json(),
        )
        data = self._parse_response(resp)
        return [YClientsBookingResult.model_validate(r) for r in data]

    # ------------------------------------------------------------------
    # 8. Reschedule booking
    # ------------------------------------------------------------------

    async def reschedule_booking(
        self,
        record_id: int,
        request: YClientsRescheduleRequest,
    ) -> None:
        resp = await self.put(
            f"/api/v1/book_record/{self.company_id}/{record_id}",
            content=request.model_dump_json(),
        )
        self._parse_response(resp)

    # ------------------------------------------------------------------
    # 9. Delete booking
    # ------------------------------------------------------------------

    async def delete_booking(self, record_id: int, record_hash: str) -> None:
        resp = await self.delete(f"/api/v1/user/records/{record_id}/{record_hash}")
        if resp.content:
            self._parse_response(resp)
