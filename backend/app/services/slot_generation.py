"""Keep a rolling window of bookable days using the existing demo opening hours."""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.domain.schedule import SlotSchedule
from app.services.unit_of_work import UnitOfWorkFactory

DAYS_AHEAD = 7


def maintain_slot_window(uow_factory: UnitOfWorkFactory) -> int:
    with uow_factory() as uow:
        laundromats = uow.laundromats.list_all()

    created = 0
    for laundromat in laundromats:
        with uow_factory() as uow:
            # Serialize with operator slot creation and other workers before checking a day.
            machines = uow.machines.list_for_laundromat(laundromat.id, lock=True)
            machine_ids = [machine.id for machine in machines if machine.reservable]
            if not machine_ids:
                continue
            now = uow.slots.now()
            timezone = ZoneInfo(laundromat.timezone)
            today = now.astimezone(timezone).date()
            for offset in range(DAYS_AHEAD):
                day = today + timedelta(days=offset)
                day_start = datetime.combine(day, time.min, timezone)
                scheduled = uow.slots.scheduled_machine_ids(machine_ids, day_start, day_start + timedelta(days=1))
                schedule = SlotSchedule.of(day, day, "08:00", "20:00", 60)
                times = schedule.slot_times(laundromat.timezone)
                wanted = [
                    (machine_id, start, end)
                    for machine_id in machine_ids if machine_id not in scheduled
                    for start, end in times if start > now
                ]
                created += uow.slots.create_many(wanted)
    return created
