"""The slot repository and unit of work against Postgres, and the same contract on the memory double."""
import threading
import time
from datetime import UTC, datetime, timedelta

import pytest

from app.data.memory import MemoryUnitOfWork
from app.domain.enums import ReservationStatus
from app.domain.slot import MachineSlot, Reservation
from tests.factories import START, make_reservation, make_slot, make_user


def new_hold(slot: MachineSlot, user_id: int, now: datetime) -> Reservation:
    r = Reservation(id=None, slot_id=slot.id, user_id=user_id, status=ReservationStatus.HELD,
                    confirmation_email="a@example.com", expires_at=now + timedelta(minutes=10))
    slot.reservations.append(r)
    return r


@pytest.fixture
def seeded(db_session):
    user, slot = make_user(db_session), make_slot(db_session)
    db_session.commit()
    return user.id, slot.id


def test_get_rebuilds_the_aggregate_with_its_reservations(db_session, uow_factory):
    user, slot = make_user(db_session), make_slot(db_session)
    make_reservation(db_session, user, slot, ReservationStatus.EXPIRED)
    db_session.commit()

    with uow_factory() as uow:
        loaded = uow.slots.get(slot.id)
    assert loaded.id == slot.id and loaded.start_time == START
    assert [r.status for r in loaded.reservations] == [ReservationStatus.EXPIRED]
    assert loaded.is_available(datetime.now(UTC))


def test_unknown_slot_is_none(db_engine, uow_factory):
    with uow_factory() as uow:
        assert uow.slots.get(999) is None
        assert uow.slots.get_for_reservation(999) is None


def test_save_inserts_and_commit_on_exit(seeded, uow_factory):
    user_id, slot_id = seeded
    with uow_factory() as uow:
        slot = uow.slots.get(slot_id, lock=True)
        hold = new_hold(slot, user_id, uow.slots.now())
        uow.slots.save(slot)
        assert hold.id is not None

    with uow_factory() as uow:
        again = uow.slots.get_for_reservation(hold.id)
    assert again.id == slot_id and not again.is_available(datetime.now(UTC))


def test_exception_rolls_everything_back(seeded, uow_factory):
    user_id, slot_id = seeded
    with pytest.raises(RuntimeError), uow_factory() as uow:
        slot = uow.slots.get(slot_id, lock=True)
        new_hold(slot, user_id, uow.slots.now())
        uow.slots.save(slot)
        raise RuntimeError("something failed after the write")

    with uow_factory() as uow:
        assert uow.slots.get(slot_id).reservations == []


def test_save_updates_existing_reservations(seeded, uow_factory):
    user_id, slot_id = seeded
    with uow_factory() as uow:
        slot = uow.slots.get(slot_id, lock=True)
        new_hold(slot, user_id, uow.slots.now())
        uow.slots.save(slot)
    with uow_factory() as uow:
        slot = uow.slots.get(slot_id, lock=True)
        slot.reservations[0].status = ReservationStatus.CANCELLED
        uow.slots.save(slot)
    with uow_factory() as uow:
        assert uow.slots.get(slot_id).reservations[0].status == ReservationStatus.CANCELLED


def test_lock_makes_a_second_writer_wait(seeded, uow_factory):
    """SELECT ... FOR UPDATE on the root: B cannot load the slot for writing until A commits."""
    _, slot_id = seeded
    a_locked, events = threading.Event(), []

    def writer_a():
        with uow_factory() as uow:
            uow.slots.get(slot_id, lock=True)
            a_locked.set()
            time.sleep(1.0)
            events.append("A commits")

    def writer_b():
        a_locked.wait()
        with uow_factory() as uow:
            uow.slots.get(slot_id, lock=True)
            events.append("B got the lock")

    threads = [threading.Thread(target=writer_a), threading.Thread(target=writer_b)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert events == ["A commits", "B got the lock"]


def test_memory_double_forgets_unsaved_changes_like_the_database():
    uow = MemoryUnitOfWork()
    uow.slots.add(MachineSlot(id=1, machine_id=1, start_time=START, end_time=START + timedelta(hours=1)))
    with uow:
        slot = uow.slots.get(1)
        new_hold(slot, 1, uow.slots.now())  # not saved
    with uow:
        assert uow.slots.get(1).reservations == []
        slot = uow.slots.get(1)
        new_hold(slot, 1, uow.slots.now())
        uow.slots.save(slot)
    assert uow.slots.get(1).reservations[0].id == 1
