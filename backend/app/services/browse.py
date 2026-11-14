"""Browse use cases: list laundromats and slots by date. Public; no token."""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.domain.availability import SlotAvailabilityRow
from app.domain.laundromat import Laundromat
from app.services.ids import LAUNDROMAT, MACHINE, SLOT, format_id
from app.services.outcome import Outcome
from app.services.unit_of_work import UnitOfWorkFactory
from app.services.views import (
    LaundromatDto,
    LaundromatListDto,
    MachineSlotsDto,
    MachineSlotsListDto,
    SlotAvailabilityDto,
)


def _laundromat_dto(lm: Laundromat) -> LaundromatDto:
    return LaundromatDto(
        laundromat_id=format_id(LAUNDROMAT, lm.id),
        name=lm.name,
        address=lm.address,
        timezone=lm.timezone,
    )


def _group_machines(rows: list[SlotAvailabilityRow]) -> list[MachineSlotsDto]:
    grouped: dict[int, list[SlotAvailabilityRow]] = {}
    order: list[int] = []
    for row in rows:
        if row.machine_id not in grouped:
            grouped[row.machine_id] = []
            order.append(row.machine_id)
        grouped[row.machine_id].append(row)

    machines: list[MachineSlotsDto] = []
    for machine_id in order:
        machine_rows = grouped[machine_id]
        first = machine_rows[0]
        machines.append(
            MachineSlotsDto(
                machine_id=format_id(MACHINE, machine_id),
                label=first.machine_label,
                type=first.machine_type,
                slots=[
                    SlotAvailabilityDto(
                        slot_id=format_id(SLOT, row.slot_id),
                        start_time=row.start_time,
                        end_time=row.end_time,
                        status="AVAILABLE" if row.available else "UNAVAILABLE",
                    )
                    for row in machine_rows
                ],
            )
        )
    return machines


class BrowseService:
    def __init__(self, uow_factory: UnitOfWorkFactory):
        self.uow_factory = uow_factory

    def list_laundromats(self) -> Outcome:
        """GET /laundromats — every laundromat, by name."""
        with self.uow_factory() as uow:
            rows = uow.laundromats.list_all()
        return Outcome.success(LaundromatListDto(laundromats=[_laundromat_dto(lm) for lm in rows]))

    def list_slots(self, laundromat_id: int, date_str: str) -> Outcome:
        """GET /laundromats/{id}/slots?date=YYYY-MM-DD — reservable machines for that local day."""
        try:
            day = date.fromisoformat(date_str)
        except ValueError:
            return Outcome.failure("invalid_request")

        with self.uow_factory() as uow:
            laundromat = uow.laundromats.get(laundromat_id)
            if laundromat is None:
                return Outcome.failure("not_found")
            try:
                tz = ZoneInfo(laundromat.timezone)
            except Exception:
                return Outcome.failure("invalid_request")
            day_start = datetime(day.year, day.month, day.day, tzinfo=tz)
            day_end = day_start + timedelta(days=1)
            rows = uow.laundromats.reservable_slots_for_day(laundromat_id, day_start, day_end)

        return Outcome.success(MachineSlotsListDto(machines=_group_machines(rows)))
