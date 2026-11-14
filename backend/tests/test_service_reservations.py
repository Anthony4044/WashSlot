"""ReservationService against the in-memory unit of work. Ownership stays in the service."""
from datetime import UTC, datetime, timedelta

import pytest

from app.data.memory import MemorySlotRepository, MemoryUnitOfWork
from app.domain.enums import ReservationStatus
from app.domain.slot import MachineSlot, Reservation
from app.services.reservations import ReservationService

NOW = datetime(2026, 11, 20, 22, 0, tzinfo=UTC)
ALICE, BOB = 1, 2


@pytest.fixture
def uow() -> MemoryUnitOfWork:
    return MemoryUnitOfWork(slots=MemorySlotRepository(clock=lambda: NOW))


@pytest.fixture
def service(uow) -> ReservationService:
    return ReservationService(uow)


def put_reservation(uow, user_id=ALICE, status=ReservationStatus.CONFIRMED, slot_id=1) -> int:
    slot = MachineSlot(
        id=slot_id,
        machine_id=4,
        start_time=NOW + timedelta(hours=1),
        end_time=NOW + timedelta(hours=2),
    )
    uow.slots.add(slot)
    slot = uow.slots.get(slot_id)
    slot.reservations.append(
        Reservation(
            id=None,
            slot_id=slot_id,
            user_id=user_id,
            status=status,
            confirmation_email="alice@example.com",
            expires_at=None if status != ReservationStatus.HELD else NOW + timedelta(minutes=10),
            confirmed_at=NOW if status == ReservationStatus.CONFIRMED else None,
        )
    )
    uow.slots.save(slot)
    return slot.reservations[0].id


def test_list_mine_newest_first(service, uow):
    older = put_reservation(uow, user_id=ALICE, slot_id=1)
    newer = put_reservation(uow, user_id=ALICE, slot_id=2)
    outcome = service.list_mine(ALICE)
    assert outcome.ok
    ids = [r.reservation_id for r in outcome.value.reservations]
    assert ids == [f"res_{newer}", f"res_{older}"]


def test_list_mine_only_shows_own(service, uow):
    put_reservation(uow, user_id=ALICE, slot_id=1)
    put_reservation(uow, user_id=BOB, slot_id=2)
    alice = service.list_mine(ALICE)
    bob = service.list_mine(BOB)
    assert len(alice.value.reservations) == 1
    assert len(bob.value.reservations) == 1
    assert alice.value.reservations[0].reservation_id != bob.value.reservations[0].reservation_id


def test_get_my_reservation(service, uow):
    reservation_id = put_reservation(uow, user_id=ALICE)
    outcome = service.get(ALICE, reservation_id)
    assert outcome.ok
    assert outcome.value.reservation_id == f"res_{reservation_id}"
    assert outcome.value.status == ReservationStatus.CONFIRMED


def test_get_someone_elses_is_not_found(service, uow):
    reservation_id = put_reservation(uow, user_id=ALICE)
    outcome = service.get(BOB, reservation_id)
    assert not outcome.ok and outcome.code == "not_found"


def test_get_unknown_is_not_found(service):
    assert service.get(ALICE, 999999).code == "not_found"


def test_cancel_my_reservation_frees_the_slot(service, uow):
    reservation_id = put_reservation(uow, user_id=ALICE)
    assert service.cancel(ALICE, reservation_id).ok
    slot = uow.slots.get(1)
    assert slot.reservation(reservation_id).status == ReservationStatus.CANCELLED
    assert slot.is_available(NOW)


def test_cancel_twice_is_ok(service, uow):
    reservation_id = put_reservation(uow, user_id=ALICE)
    assert service.cancel(ALICE, reservation_id).ok
    assert service.cancel(ALICE, reservation_id).ok


def test_cancel_someone_elses_is_not_found(service, uow):
    reservation_id = put_reservation(uow, user_id=ALICE)
    assert service.cancel(BOB, reservation_id).code == "not_found"


def test_cancel_after_slot_start_is_too_late():
    clock = {"now": NOW}

    def tick():
        return clock["now"]

    uow = MemoryUnitOfWork(slots=MemorySlotRepository(clock=tick))
    service = ReservationService(uow)
    reservation_id = put_reservation(uow, user_id=ALICE)
    clock["now"] = NOW + timedelta(hours=1)  # == slot.start_time
    assert service.cancel(ALICE, reservation_id).code == "too_late_to_cancel"
