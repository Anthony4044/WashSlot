"""Operator use cases (US-7.1, US-7.2 and US-7.3), in the SERVICE layer:
- my laundromats          GET   /operator/laundromats
- their machines          GET   /operator/laundromats/{id}/machines
- reservable on/off       PATCH /operator/laundromats/{id}/machines/{machineId}
- create slots            POST  /operator/laundromats/{id}/slots
- today's bookings        GET   /operator/laundromats/{id}/today
- my emails               GET   /operator/notifications?status=FAILED
- send one again          POST  /operator/notifications/{id}/retry

Ownership is checked HERE, on every use case: the scope (operator:manage) only says "you are an
operator", not "of which laundromat". Another operator's laundromat, or a machine or an email that
isn't in one of mine, is not_found, exactly like an id that doesn't exist: we never reveal it is there.
"""
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.domain.enums import OutboxStatus
from app.domain.errors import DomainError
from app.domain.laundromat import Laundromat
from app.domain.schedule import SlotSchedule
from app.services.ids import RESERVATION, format_id
from app.services.outcome import Outcome
from app.services.unit_of_work import UnitOfWork, UnitOfWorkFactory
from app.services.views import (
    LaundromatListDto,
    MachineListDto,
    NotificationListDto,
    SlotsCreatedDto,
    TodayBookingDto,
    TodayBookingsDto,
    laundromat_dto,
    machine_dto,
    notification_dto,
)

MAX_NOTIFICATIONS = 100  # the newest ones; the contract says "at most 100"


class OperatorService:
    def __init__(self, uow_factory: UnitOfWorkFactory):
        self.uow_factory = uow_factory

    def list_laundromats(self, user_id: int) -> Outcome:
        """The laundromats the caller operates (usually one)."""
        with self.uow_factory() as uow:
            mine = uow.laundromats.list_for_operator(user_id)
        return Outcome.success(LaundromatListDto(laundromats=[laundromat_dto(lm) for lm in mine]))

    def today(self, user_id: int, laundromat_id: int) -> Outcome:
        """Confirmed bookings and no-shows for the local calendar day."""
        with self.uow_factory() as uow:
            laundromat = _own_laundromat(uow, user_id, laundromat_id)
            if laundromat is None:
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

    def list_machines(self, user_id: int, laundromat_id: int) -> Outcome:
        """Every machine of one of the caller's laundromats, reservable or not."""
        with self.uow_factory() as uow:
            if _own_laundromat(uow, user_id, laundromat_id) is None:
                return Outcome.failure("not_found")
            machines = uow.machines.list_for_laundromat(laundromat_id)
        return Outcome.success(MachineListDto(machines=[machine_dto(m) for m in machines]))

    def set_reservable(self, user_id: int, laundromat_id: int, machine_id: int, reservable: bool) -> Outcome:
        """Switch a machine on (reservable) or off (walk-in only). Idempotent: the same value twice is a no-op."""
        with self.uow_factory() as uow:
            if _own_laundromat(uow, user_id, laundromat_id) is None:
                return Outcome.failure("not_found")
            machine = uow.machines.get(machine_id)
            if machine is None or not machine.belongs_to(laundromat_id):
                return Outcome.failure("not_found")  # a machine of ANOTHER laundromat: never touch it
            machine.set_reservable(reservable)
            uow.machines.save(machine)
        return Outcome.success(machine_dto(machine))

    def create_slots(
        self,
        user_id: int,
        laundromat_id: int,
        *,
        from_date: date,
        to_date: date,
        open_time: str,
        close_time: str,
        slot_minutes: int,
        machine_ids: list[int] | None = None,
    ) -> Outcome:
        """Slots for a date range, in the laundromat's own time zone. Existing or started slots are skipped.

        machine_ids None means every reservable machine. Idempotent: the database's unique
        (machine_id, start_time) skips what already exists, so a repeat creates nothing more.
        """
        try:
            schedule = SlotSchedule.of(from_date, to_date, open_time, close_time, slot_minutes)
        except DomainError as refused:
            return Outcome.failure(refused.code)  # invalid_request: the form's rules (domain/schedule.py)

        with self.uow_factory() as uow:
            laundromat = _own_laundromat(uow, user_id, laundromat_id)
            if laundromat is None:
                return Outcome.failure("not_found")
            machines = {m.id: m for m in uow.machines.list_for_laundromat(laundromat_id)}
            if machine_ids is None:
                chosen = [m for m in machines.values() if m.reservable]
            elif all(i in machines for i in machine_ids):
                chosen = [machines[i] for i in machine_ids]
            else:
                return Outcome.failure("not_found")  # a machine of another laundromat (or none at all)

            times = schedule.slot_times(laundromat.timezone)
            now = uow.slots.now()  # the database clock: a slot that already started is never created
            wanted = [(m.id, start, end) for m in chosen for start, end in times if start > now]
            created = uow.slots.create_many(wanted)
        return Outcome.success(SlotsCreatedDto(created=created, skipped=len(chosen) * len(times) - created))

    def list_notifications(self, user_id: int, status: OutboxStatus | None = None) -> Outcome:
        """The confirmation emails of every laundromat the caller operates, newest first.

        Ownership is the query itself: we only ever ask for the caller's own laundromat ids.
        """
        with self.uow_factory() as uow:
            mine = {lm.id: lm for lm in uow.laundromats.list_for_operator(user_id)}
            messages = uow.outbox.list_for_laundromats(list(mine), status, MAX_NOTIFICATIONS)
        return Outcome.success(NotificationListDto(
            notifications=[notification_dto(m, mine[m.laundromat_id]) for m in messages]))

    def retry_notification(self, user_id: int, notification_id: int) -> Outcome:
        """Put a FAILED email back in the queue (the domain rule: OutboxMessage.retry). Idempotent.

        Nothing is sent here: the worker sends it within seconds, outside any request, exactly like
        the first time. The row is locked so two retries at once can't both change it.
        """
        with self.uow_factory() as uow:
            message = uow.outbox.get(notification_id, lock=True)
            laundromat = None if message is None else _own_laundromat(uow, user_id, message.laundromat_id)
            if laundromat is None:
                return Outcome.failure("not_found")  # no such email, or another operator's
            if message.retry(uow.slots.now()):  # the database clock: due right now
                uow.outbox.save(message)
        return Outcome.success(notification_dto(message, laundromat))


def _own_laundromat(uow: UnitOfWork, user_id: int, laundromat_id: int) -> Laundromat | None:
    """The laundromat, if this user operates it; otherwise None (the caller answers not_found)."""
    laundromat = uow.laundromats.get(laundromat_id)
    return laundromat if laundromat is not None and laundromat.is_run_by(user_id) else None
