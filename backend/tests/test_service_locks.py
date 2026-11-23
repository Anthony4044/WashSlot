"""Concurrency at the service level (US-8.4): every write reads its row with a lock first.

Two customers clicking at the same moment are served one after the other because each use case
reads the slot with SELECT ... FOR UPDATE before deciding (see HoldService.place_hold). The memory
double has no real locks, so tests/test_hold_race.py proves the lock on Postgres. What a service
test CAN prove is that every use case asks for it. The stores below refuse to save a slot (or an
email) that this unit of work did not read with lock=True. A service that forgets the lock fails here.
"""
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.data.memory import MemoryOutboxRepository, MemorySlotRepository, MemoryUnitOfWork
from app.domain.enums import OutboxStatus, ReservationStatus
from app.domain.laundromat import Laundromat
from app.domain.notification import CONFIRMATION_EMAIL, MAX_ATTEMPTS, OutboxMessage
from app.domain.slot import MachineSlot
from app.services.holds import HoldService
from app.services.operator import OperatorService
from app.services.reservations import ReservationService

NOW = datetime(2030, 1, 7, 17, 0, tzinfo=UTC)
CUSTOMER, OPERATOR = 1, 9
SLOT = 1


class LockCheckingSlots(MemorySlotRepository):
    """Remembers which slots this unit of work read with lock=True, and refuses to save any other."""

    def __init__(self, clock):
        super().__init__(clock=clock)
        self.locked: set[int] = set()
        self.saved: list[int] = []

    def get(self, slot_id, *, lock=False):
        return self._remember(super().get(slot_id, lock=lock), lock)

    def get_for_reservation(self, reservation_id, *, lock=False):
        return self._remember(super().get_for_reservation(reservation_id, lock=lock), lock)

    def _remember(self, slot, lock):
        if slot is not None and lock:
            self.locked.add(slot.id)
        return slot

    def save(self, slot):
        if slot.id not in self.locked:
            raise AssertionError(f"slot {slot.id} was saved without being read with lock=True first")
        self.saved.append(slot.id)
        super().save(slot)


class LockCheckingOutbox(MemoryOutboxRepository):
    """The same check for emails, which an operator's retry changes (US-7.3)."""

    def __init__(self, clock):
        super().__init__(clock=clock)
        self.locked: set[int] = set()
        self.saved: list[int] = []

    def get(self, message_id, *, lock=False):
        message = super().get(message_id, lock=lock)
        if message is not None and lock:
            self.locked.add(message.id)
        return message

    def save(self, message):
        if message.id not in self.locked:
            raise AssertionError(f"email {message.id} was saved without being read with lock=True first")
        self.saved.append(message.id)
        super().save(message)


class LockCheckingUnitOfWork(MemoryUnitOfWork):
    """Each `with` is a new transaction, so it starts with no locks (COMMIT released the last ones)."""

    def __enter__(self):
        self.slots.locked.clear()
        self.outbox.locked.clear()
        return super().__enter__()


class Clock:
    def __init__(self):
        self.now = NOW

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def uow(clock) -> LockCheckingUnitOfWork:
    """One free slot (in an hour) at Spin City, which OPERATOR runs."""
    uow = LockCheckingUnitOfWork(slots=LockCheckingSlots(clock), outbox=LockCheckingOutbox(clock))
    uow.laundromats.add(Laundromat(1, "Spin City", "1 Main St", "America/Toronto", operator_id=OPERATOR))
    uow.slots.add(MachineSlot(id=SLOT, machine_id=1, start_time=NOW + timedelta(hours=1),
                              end_time=NOW + timedelta(hours=2)))
    return uow


def number(public_id: str) -> int:
    return int(public_id.rsplit("_", 1)[1])


def hold(uow) -> int:
    outcome = HoldService(uow).place_hold(CUSTOMER, SLOT, "kim@example.com", str(uuid4()))
    assert outcome.ok, outcome.code
    return number(outcome.value.hold_id)


def book(uow) -> int:
    hold_id = hold(uow)
    assert HoldService(uow).confirm(CUSTOMER, hold_id).ok
    return hold_id  # a confirmed hold keeps its id: it is the reservation now


def status(uow) -> ReservationStatus:
    [reservation] = uow.slots.get(SLOT).reservations
    return reservation.status


# --- the checker itself --------------------------------------------------------------------------

def test_the_checker_catches_a_save_without_the_lock(uow):
    with uow:
        slot = uow.slots.get(SLOT)  # no lock
        with pytest.raises(AssertionError, match="without being read with lock=True"):
            uow.slots.save(slot)


def test_a_lock_from_an_earlier_unit_of_work_does_not_count(uow):
    with uow:
        slot = uow.slots.get(SLOT, lock=True)
    with uow:  # COMMIT released the lock; this transaction must take its own
        with pytest.raises(AssertionError):
            uow.slots.save(slot)


# --- every write on a slot locks it first ----------------------------------------------------------

def test_placing_a_hold_locks_the_slot(uow):
    hold(uow)

    assert uow.slots.saved == [SLOT]
    assert status(uow) == ReservationStatus.HELD


def test_a_refused_hold_writes_nothing(uow):
    hold(uow)
    refused = HoldService(uow).place_hold(2, SLOT, "lee@example.com", str(uuid4()))

    assert refused.code == "slot_unavailable"
    assert uow.slots.saved == [SLOT]  # only the first hold was written


def test_confirming_locks_the_slot(uow):
    book(uow)

    assert uow.slots.saved == [SLOT, SLOT]
    assert status(uow) == ReservationStatus.CONFIRMED


def test_cancelling_locks_the_slot(uow):
    reservation_id = book(uow)

    assert ReservationService(uow).cancel(CUSTOMER, reservation_id).ok
    assert status(uow) == ReservationStatus.CANCELLED


@pytest.mark.parametrize(("user_id", "is_operator"), [(CUSTOMER, False), (OPERATOR, True)])
def test_checking_in_locks_the_slot(uow, clock, user_id, is_operator):
    reservation_id = book(uow)
    clock.now = NOW + timedelta(hours=1, minutes=5)  # just after the start: check-in is open

    checked_in = ReservationService(uow).check_in(user_id, reservation_id, is_operator=is_operator)

    assert checked_in.ok, checked_in.code
    assert checked_in.value.checked_in_at == clock.now


def test_marking_a_no_show_locks_the_slot(uow, clock):
    book(uow)
    clock.now = NOW + timedelta(hours=1, minutes=16)  # 16 minutes after the start, nobody came

    assert ReservationService(uow).mark_no_shows() == 1
    assert status(uow) == ReservationStatus.NO_SHOW


# --- an operator's retry locks the email ---------------------------------------------------------------

def test_retrying_a_failed_email_locks_it(uow):
    start = NOW + timedelta(hours=1)
    payload = {"to": "kim@example.com", "laundromatName": "Spin City", "laundromatAddress": "1 Main St",
               "machineLabel": "Washer 1", "machineType": "WASHER", "startTime": start.isoformat(),
               "endTime": (start + timedelta(hours=1)).isoformat(), "timezone": "America/Toronto"}
    uow.outbox.add(OutboxMessage(
        id=None, reservation_id=70, laundromat_id=1, type=CONFIRMATION_EMAIL, payload=payload,
        next_attempt_at=NOW, status=OutboxStatus.FAILED, attempts=MAX_ATTEMPTS, last_error="503"))
    [email_id] = uow.outbox.messages

    assert OperatorService(uow).retry_notification(OPERATOR, email_id).ok
    assert uow.outbox.saved == [email_id]
    assert uow.outbox.messages[email_id].status == OutboxStatus.PENDING
