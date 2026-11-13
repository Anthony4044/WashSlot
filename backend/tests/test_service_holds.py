"""HoldService (get a hold, confirm it) against the in-memory unit of work. No database, no HTTP."""
from datetime import UTC, datetime, timedelta

import pytest

from app.data.memory import MemorySlotRepository, MemoryUnitOfWork
from app.domain.enums import ReservationStatus
from app.domain.slot import MachineSlot, Reservation
from app.services.holds import HoldService

NOW = datetime(2026, 11, 20, 22, 0, tzinfo=UTC)
ALICE, BOB = 1, 2


class Clock:
    """The 'database clock' of the memory double; tests move it forward."""

    def __init__(self):
        self.now = NOW

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def uow(clock) -> MemoryUnitOfWork:
    return MemoryUnitOfWork(slots=MemorySlotRepository(clock=clock))


@pytest.fixture
def service(uow) -> HoldService:
    return HoldService(uow)


def put_hold(uow, user_id=ALICE, status=ReservationStatus.HELD, expires_in_min=10) -> int:
    """Arrange: slot 1 with one reservation of `user_id`. Returns the hold's id."""
    slot = MachineSlot(id=1, machine_id=4, start_time=NOW + timedelta(hours=1), end_time=NOW + timedelta(hours=2))
    uow.slots.add(slot)
    slot = uow.slots.get(1)
    slot.reservations.append(Reservation(id=None, slot_id=1, user_id=user_id, status=status,
                                         confirmation_email="alice@example.com",
                                         expires_at=NOW + timedelta(minutes=expires_in_min)))
    uow.slots.save(slot)
    return slot.reservations[0].id


def stored_status(uow, hold_id) -> ReservationStatus:
    return uow.slots.get_for_reservation(hold_id).reservation(hold_id).status


# --- get_hold -------------------------------------------------------------------------------

def test_get_my_hold(service, uow):
    hold_id = put_hold(uow)
    outcome = service.get_hold(ALICE, hold_id)
    assert outcome.ok
    body = outcome.value.model_dump(mode="json", by_alias=True)
    assert body["holdId"] == f"hold_{hold_id}" and body["slotId"] == "slot_1"
    assert body["status"] == "HELD" and body["machineLabel"] == "Washer 4" and body["laundromatId"] == "lm_1"
    assert body["expiresAt"] == "2026-11-20T22:10:00Z"


def test_someone_elses_hold_is_not_found(service, uow):
    hold_id = put_hold(uow, user_id=BOB)
    assert service.get_hold(ALICE, hold_id).code == "not_found"


def test_unknown_hold_is_not_found(service, uow):
    assert service.get_hold(ALICE, 999).code == "not_found"


def test_a_stale_hold_shows_expired_without_writing_anything(service, uow, clock):
    hold_id = put_hold(uow)
    clock.now = NOW + timedelta(minutes=11)
    assert service.get_hold(ALICE, hold_id).value.status == ReservationStatus.EXPIRED
    assert stored_status(uow, hold_id) == ReservationStatus.HELD  # a read never writes


# --- confirm --------------------------------------------------------------------------------

def test_confirm_my_live_hold(service, uow):
    hold_id = put_hold(uow)
    outcome = service.confirm(ALICE, hold_id)
    assert outcome.ok
    body = outcome.value.model_dump(mode="json", by_alias=True)
    assert body["reservationId"] == f"res_{hold_id}" and body["status"] == "CONFIRMED"
    assert body["checkedInAt"] is None
    assert stored_status(uow, hold_id) == ReservationStatus.CONFIRMED


def test_confirm_twice_gives_the_same_reservation(service, uow, clock):
    hold_id = put_hold(uow)
    first = service.confirm(ALICE, hold_id)
    clock.now = NOW + timedelta(minutes=30)  # a retry long after the hold would have expired
    again = service.confirm(ALICE, hold_id)
    assert again.ok and again.value == first.value


def test_confirm_after_expiry_is_hold_expired_and_writes_nothing(service, uow, clock):
    hold_id = put_hold(uow)
    clock.now = NOW + timedelta(minutes=10)  # exactly at expiresAt: too late
    assert service.confirm(ALICE, hold_id).code == "hold_expired"
    assert stored_status(uow, hold_id) == ReservationStatus.HELD


def test_confirm_a_hold_the_worker_already_expired(service, uow):
    hold_id = put_hold(uow, status=ReservationStatus.EXPIRED, expires_in_min=-5)
    assert service.confirm(ALICE, hold_id).code == "hold_expired"


def test_confirm_a_cancelled_reservation_is_already_cancelled(service, uow):
    hold_id = put_hold(uow, status=ReservationStatus.CANCELLED)
    assert service.confirm(ALICE, hold_id).code == "already_cancelled"


def test_confirm_someone_elses_hold_is_not_found_and_changes_nothing(service, uow):
    hold_id = put_hold(uow, user_id=BOB)
    assert service.confirm(ALICE, hold_id).code == "not_found"
    assert stored_status(uow, hold_id) == ReservationStatus.HELD


def test_confirm_someone_elses_expired_hold_is_still_not_found(service, uow):
    """Ownership is checked first, so the answer never hints that the hold exists."""
    hold_id = put_hold(uow, user_id=BOB, expires_in_min=-5)
    assert service.confirm(ALICE, hold_id).code == "not_found"


def test_confirm_an_unknown_hold_is_not_found(service):
    assert service.confirm(ALICE, 999).code == "not_found"
