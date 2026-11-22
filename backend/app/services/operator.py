"""Read the operator's assigned laundromats and their bookings for today."""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.services.ids import RESERVATION, format_id
from app.services.outcome import Outcome
from app.services.unit_of_work import UnitOfWorkFactory
from app.services.views import LaundromatListDto, TodayBookingDto, TodayBookingsDto, laundromat_dto


class OperatorService:
    def __init__(self, uow_factory: UnitOfWorkFactory):
        self.uow_factory = uow_factory

    def list_laundromats(self, operator_id: int) -> Outcome:
        with self.uow_factory() as uow:
            rows = uow.laundromats.list_for_operator(operator_id)
        return Outcome.success(LaundromatListDto(laundromats=[laundromat_dto(row) for row in rows]))

    def today(self, operator_id: int, laundromat_id: int) -> Outcome:
        with self.uow_factory() as uow:
            laundromat = uow.laundromats.get(laundromat_id)
            if laundromat is None or laundromat.operator_id != operator_id:
                return Outcome.failure("not_found")
            timezone = ZoneInfo(laundromat.timezone)
            day = uow.slots.now().astimezone(timezone).date()
            day_start = datetime.combine(day, time.min, timezone)
            rows = uow.laundromats.bookings_for_day(laundromat_id, day_start, day_start + timedelta(days=1))

        return Outcome.success(TodayBookingsDto(
            date=day,
            reservations=[
                TodayBookingDto(
                    reservation_id=format_id(RESERVATION, row.reservation_id),
                    machine_label=row.machine_label,
                    start_time=row.start_time,
                    end_time=row.end_time,
                    customer_email=row.customer_email,
                    status=row.status,
                    checked_in_at=row.checked_in_at,
                )
                for row in rows
            ],
        ))
