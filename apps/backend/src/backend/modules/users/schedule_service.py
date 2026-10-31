from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from src.backend.modules.companies.models import Company
from src.backend.modules.users.models import CompanyUser, UserRole
from src.backend.modules.users.schemas import ManagerScheduleInfo, WorkSchedule


class ScheduleService:
    DAY_NAMES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

    def _parse_work_schedule(self, company_user: CompanyUser) -> WorkSchedule | None:
        if company_user.work_schedule is None:
            return None
        return WorkSchedule.model_validate(company_user.work_schedule)

    def _get_current_time_in_timezone(self, timezone_str: str) -> datetime:
        tz = ZoneInfo(timezone_str)
        return datetime.now(tz)

    def _get_day_name(self, weekday: int) -> str:
        return self.DAY_NAMES[weekday]

    def _time_in_slot(self, current_time: datetime, slot_start: str, slot_end: str) -> bool:
        start_hour, start_minute = map(int, slot_start.split(":"))
        end_hour, end_minute = map(int, slot_end.split(":"))
        slot_start_time = time(start_hour, start_minute)
        slot_end_time = time(end_hour, end_minute)
        current_time_only = current_time.time()
        return slot_start_time <= current_time_only < slot_end_time

    def is_manager_working_now(self, company_user: CompanyUser) -> bool:
        if not company_user.is_available:
            return False

        schedule = self._parse_work_schedule(company_user)
        if schedule is None:
            return False

        current_time = self._get_current_time_in_timezone(schedule.timezone)
        day_name = self._get_day_name(current_time.weekday())
        day_slots = getattr(schedule.weekly, day_name)

        if not day_slots:
            return False

        for slot in day_slots:
            if self._time_in_slot(current_time, slot.start, slot.end):
                return True

        return False

    def get_next_working_time(self, company_user: CompanyUser) -> datetime | None:
        schedule = self._parse_work_schedule(company_user)
        if schedule is None:
            return None

        tz = ZoneInfo(schedule.timezone)
        current_time = datetime.now(tz)
        current_weekday = current_time.weekday()

        for day_offset in range(7):
            check_weekday = (current_weekday + day_offset) % 7
            day_name = self._get_day_name(check_weekday)
            day_slots = getattr(schedule.weekly, day_name)

            if not day_slots:
                continue

            slot = day_slots[0]
            start_hour, start_minute = map(int, slot.start.split(":"))

            check_date = current_time.date() + timedelta(days=day_offset)
            candidate_datetime = datetime.combine(check_date, time(start_hour, start_minute), tz)

            if day_offset == 0:
                if candidate_datetime > current_time:
                    return candidate_datetime
            else:
                return candidate_datetime

        return None

    async def get_available_managers(self, company: Company) -> list[CompanyUser]:
        managers = (
            await CompanyUser.filter(
                company=company,
                is_available=True,
                work_schedule__not_isnull=True,
            )
            .exclude(role=UserRole.VIEWER)
            .all()
        )

        return list(managers)

    def schedule_description(self, company_user: CompanyUser) -> str | None:
        schedule = self._parse_work_schedule(company_user)
        if schedule is None:
            return None

        day_names_ru = {
            "mon": "Пн",
            "tue": "Вт",
            "wed": "Ср",
            "thu": "Чт",
            "fri": "Пт",
            "sat": "Сб",
            "sun": "Вс",
        }

        day_slots_map = {}
        for day_name in self.DAY_NAMES:
            slots = getattr(schedule.weekly, day_name)
            if slots:
                slot = slots[0]
                slot_key = f"{slot.start}-{slot.end}"
                if slot_key not in day_slots_map:
                    day_slots_map[slot_key] = []
                day_slots_map[slot_key].append(day_name)

        if not day_slots_map:
            return None

        parts = []
        for slot_key, days in sorted(day_slots_map.items()):
            start, end = slot_key.split("-")
            if len(days) == 1:
                day_ru = day_names_ru[days[0]]
                parts.append(f"{day_ru} {start}-{end}")
            elif len(days) == 7:
                parts.append(f"Пн-Вс {start}-{end}")
            else:
                day_ru_list = [day_names_ru[d] for d in sorted(days, key=lambda x: self.DAY_NAMES.index(x))]
                if len(day_ru_list) > 1 and day_ru_list[0] == "Пн" and day_ru_list[-1] == "Пт":
                    parts.append(f"Пн-Пт {start}-{end}")
                else:
                    parts.append(f"{'-'.join(day_ru_list)} {start}-{end}")

        result = ", ".join(parts)
        return f"{result} ({schedule.timezone})"

    def get_manager_schedule_info(self, company_user: CompanyUser) -> ManagerScheduleInfo:
        """Get complete schedule information for a manager.

        Args:
            company_user: CompanyUser instance

        Returns:
            ManagerScheduleInfo with schedule, working status, and next working time
        """
        schedule = self._parse_work_schedule(company_user)
        is_working = self.is_manager_working_now(company_user)
        next_working_time = self.get_next_working_time(company_user)
        schedule_description = self.schedule_description(company_user)

        return ManagerScheduleInfo(
            schedule=schedule,
            is_working=is_working,
            next_working_time=next_working_time,
            schedule_description=schedule_description,
        )


schedule_service = ScheduleService()
