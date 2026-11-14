"""HoldService.place_hold against the in-memory unit of work. No database, no HTTP (lecture Ch. 5).

The service never touches SQL, so it can run on app/data/memory.py's unit of work. Its "database
clock" is a Clock object that each test can move forward. The checks are on Outcomes ("not_found",
"slot_unavailable"), never on status codes: turning a code into 404 or 409 is the interface's job.

What these tests can't show is the lock: the memory double has none. tests/test_hold_race.py
proves the lock on the real database.
"""
from datetime import UTC, datetime, timedelta

import pytest

from app.data.memory import MemorySlotRepository, MemoryUnitOfWork
from app.domain.enums import ReservationStatus
from app.domain.slot import MachineSlot, Reservation
from app.services.holds import HoldService

NOW = datetime(2026, 11, 20, 22, 0, tzinfo=UTC)
ALICE, BOB = 1, 2
SLOT = 1


class Clock:
    """Stands in for the database clock (SELECT now()); a test can move it forward."""

    def __init__(self):
        self.now = NOW

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def uow(clock) -> MemoryUnitOfWork:
    """An in-memory unit of work holding one free slot (slot 1: Washer 1 at Spin City, in an hour)."""
    uow = MemoryUnitOfWork(slots=MemorySlotRepository(clock=clock))
    uow.slots.add(MachineSlot(id=SLOT, machine_id=1, start_time=NOW + timedelta(hours=1),
                              end_time=NOW + timedelta(hours=2)))
    return uow


@pytest.fixture
def service(uow) -> HoldService:
    return HoldService(uow)  # 10-minute holds, the default


def put_reservation(uow, user_id: int, status: ReservationStatus, expires_in_min: int = 10) -> None:
    """Arrange: give slot 1 a reservation (someone else's hold, say), the same way the app saves one."""
    slot = uow.slots.get(SLOT)
    slot.reservations.append(Reservation(id=None, slot_id=SLOT, user_id=user_id, status=status,
                                         confirmation_email="bob@example.com",
                                         expires_at=NOW + timedelta(minutes=expires_in_min)))
    uow.slots.save(slot)


def stored(uow) -> list[tuple[int, ReservationStatus]]:
    """What is saved for slot 1 now, as (user id, status) pairs."""
    return [(r.user_id, r.status) for r in uow.slots.get(SLOT).reservations]


# --- success ----------------------------------------------------------------------------------

def test_place_hold_returns_the_new_hold(service, uow):
    outcome = service.place_hold(ALICE, SLOT, "alice@example.com")

    assert outcome.ok
    body = outcome.value.model_dump(mode="json", by_alias=True)  # exactly what the API will send
    assert body["holdId"] == "hold_1"
    assert body["slotId"] == "slot_1"
    assert body["status"] == "HELD"
    assert body["expiresAt"] == "2026-11-20T22:10:00Z"  # the clock's NOW + 10 minutes
    assert body["confirmationEmail"] == "alice@example.com"
    assert body["laundromatName"] == "Spin City"  # where and when, from the slot's details
    assert stored(uow) == [(ALICE, ReservationStatus.HELD)]  # and it was saved


def test_the_hold_lasts_hold_minutes(uow):
    outcome = HoldService(uow, hold_minutes=15).place_hold(ALICE, SLOT, "alice@example.com")
    assert outcome.value.expires_at == NOW + timedelta(minutes=15)


# --- refusals ---------------------------------------------------------------------------------

def test_unknown_slot_is_not_found(service):
    outcome = service.place_hold(ALICE, 999, "alice@example.com")
    assert not outcome.ok
    assert outcome.code == "not_found"


@pytest.mark.parametrize("taken_by", [ReservationStatus.HELD, ReservationStatus.CONFIRMED])
def test_a_taken_slot_is_slot_unavailable_and_nothing_is_saved(service, uow, taken_by):
    put_reservation(uow, BOB, taken_by)
    outcome = service.place_hold(ALICE, SLOT, "alice@example.com")
    assert outcome.code == "slot_unavailable"
    assert stored(uow) == [(BOB, taken_by)]  # Alice's hold was never written


def test_holding_my_own_slot_again_is_slot_unavailable(service):
    assert service.place_hold(ALICE, SLOT, "alice@example.com").ok
    assert service.place_hold(ALICE, SLOT, "alice@example.com").code == "slot_unavailable"


# --- expiry: the database clock decides --------------------------------------------------------

def test_an_expired_hold_on_the_slot_allows_a_new_hold(service, uow, clock):
    put_reservation(uow, BOB, ReservationStatus.HELD, expires_in_min=10)
    clock.now = NOW + timedelta(minutes=11)  # Bob's 10 minutes ran out a minute ago

    outcome = service.place_hold(ALICE, SLOT, "alice@example.com")

    assert outcome.ok
    # Bob's hold was marked EXPIRED and saved in the same unit of work as Alice's new hold.
    assert stored(uow) == [(BOB, ReservationStatus.EXPIRED), (ALICE, ReservationStatus.HELD)]


def test_a_hold_counts_until_the_last_second(service, uow, clock):
    put_reservation(uow, BOB, ReservationStatus.HELD, expires_in_min=10)

    clock.now = NOW + timedelta(minutes=10) - timedelta(seconds=1)  # one second left
    assert service.place_hold(ALICE, SLOT, "alice@example.com").code == "slot_unavailable"

    clock.now = NOW + timedelta(minutes=10)  # exactly at expiresAt: it has lapsed
    assert service.place_hold(ALICE, SLOT, "alice@example.com").ok


@pytest.mark.parametrize("ended", [ReservationStatus.EXPIRED, ReservationStatus.CANCELLED,
                                   ReservationStatus.NO_SHOW])
def test_ended_reservations_do_not_block_a_new_hold(service, uow, ended):
    put_reservation(uow, BOB, ended)
    assert service.place_hold(ALICE, SLOT, "alice@example.com").ok
