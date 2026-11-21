"""US-5.1: holds expire on their own.

What we prove:
- an abandoned hold frees its slot with the worker OFF (lazy expiry on every request)
- the worker job marks stale holds EXPIRED in the database, and touches nothing else
- confirming right at the expiry time gives one clear answer: hold_expired
- the worker loop runs due jobs and survives a job that crashes
"""
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

import worker
from app.data.memory import MemorySlotRepository, MemoryUnitOfWork
from app.data.tables import ReservationRow
from app.domain.enums import ReservationStatus
from app.domain.slot import MachineSlot, Reservation
from app.services.holds import HoldService
from app.services.reservations import ReservationService
from tests.factories import make_reservation, make_slot, make_user

NOW = datetime(2030, 1, 7, 17, 0, tzinfo=UTC)  # any fixed time works: the memory clock is ours
ALICE, BOB = 1, 2


class Clock:
    """The 'database clock' for the memory double. Tests move it forward."""

    def __init__(self):
        self.now = NOW

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def uow(clock) -> MemoryUnitOfWork:
    store = MemoryUnitOfWork(slots=MemorySlotRepository(clock=clock))
    # One free slot, starting in 2 hours.
    store.slots.add(MachineSlot(id=1, machine_id=4, start_time=NOW + timedelta(hours=2),
                                end_time=NOW + timedelta(hours=3)))
    return store


def hold_for(uow, user_id) -> int:
    """Place a 10-minute hold on slot 1 through the service. Returns the hold id."""
    outcome = HoldService(uow).place_hold(user_id, 1, "someone@example.com")
    assert outcome.ok, outcome.code
    return int(outcome.value.hold_id.removeprefix("hold_"))


# --- The domain rule ------------------------------------------------------------------------

def held(expires_at) -> Reservation:
    return Reservation(id=1, slot_id=1, user_id=ALICE, status=ReservationStatus.HELD,
                       confirmation_email="a@example.com", expires_at=expires_at)


def test_a_hold_past_its_expiry_becomes_expired():
    r = held(NOW - timedelta(seconds=1))
    assert r.expire_if_stale(NOW) is True
    assert r.status == ReservationStatus.EXPIRED


def test_a_hold_at_exactly_its_expiry_is_expired():
    r = held(NOW)
    assert r.expire_if_stale(NOW) is True


def test_a_live_hold_is_left_alone():
    r = held(NOW + timedelta(seconds=1))
    assert r.expire_if_stale(NOW) is False
    assert r.status == ReservationStatus.HELD


def test_a_confirmed_reservation_never_expires():
    r = held(NOW - timedelta(minutes=5))
    r.status = ReservationStatus.CONFIRMED
    assert r.expire_if_stale(NOW) is False
    assert r.status == ReservationStatus.CONFIRMED


# --- Lazy expiry: no worker needed ----------------------------------------------------------

def test_an_abandoned_hold_frees_the_slot_without_the_worker(uow, clock):
    alice_hold = hold_for(uow, ALICE)
    assert HoldService(uow).place_hold(BOB, 1, "bob@example.com").code == "slot_unavailable"

    clock.now += timedelta(minutes=10)  # Alice walks away; the worker is not running

    hold_for(uow, BOB)  # Bob gets the slot
    alice_view = ReservationService(uow).get(ALICE, alice_hold).value
    assert alice_view.status == ReservationStatus.EXPIRED


def test_my_reservations_show_a_stale_hold_as_expired(uow, clock):
    hold_for(uow, ALICE)
    clock.now += timedelta(minutes=11)
    listed = ReservationService(uow).list_mine(ALICE).value.reservations
    assert [r.status for r in listed] == [ReservationStatus.EXPIRED]


def test_confirm_right_at_expiry_is_hold_expired_with_or_without_the_worker(uow, clock):
    hold_id = hold_for(uow, ALICE)
    clock.now += timedelta(minutes=10)  # exactly the expiry time

    assert HoldService(uow).confirm(ALICE, hold_id).code == "hold_expired"  # worker not run yet
    HoldService(uow).expire_stale_holds()
    assert HoldService(uow).confirm(ALICE, hold_id).code == "hold_expired"  # same answer after it ran


def test_confirm_one_second_before_expiry_still_works(uow, clock):
    hold_id = hold_for(uow, ALICE)
    clock.now += timedelta(minutes=10) - timedelta(seconds=1)
    assert HoldService(uow).confirm(ALICE, hold_id).ok


# --- The worker job on the real database ----------------------------------------------------

def test_the_worker_job_expires_only_stale_holds(uow_factory, db_session):
    alice, bob, carol = (make_user(db_session, f"{n}@example.com") for n in ("alice", "bob", "carol"))
    an_hour_ago = datetime.now(UTC) - timedelta(hours=1)
    stale = make_reservation(db_session, alice, make_slot(db_session, label="W1"), expires_at=an_hour_ago)
    live = make_reservation(db_session, bob, make_slot(db_session, label="W2"))  # 10 minutes left
    confirmed = make_reservation(db_session, carol, make_slot(db_session, label="W3"),
                                 ReservationStatus.CONFIRMED, expires_at=an_hour_ago)
    db_session.commit()

    worker.expire_holds(uow_factory)

    db_session.expire_all()  # read fresh values from the database
    status = {row.id: row.status for row in db_session.scalars(select(ReservationRow))}
    assert status[stale.id] == ReservationStatus.EXPIRED
    assert status[live.id] == ReservationStatus.HELD
    assert status[confirmed.id] == ReservationStatus.CONFIRMED


def test_running_the_job_twice_changes_nothing_more(uow_factory, db_session):
    user = make_user(db_session)
    make_reservation(db_session, user, make_slot(db_session), expires_at=datetime.now(UTC) - timedelta(hours=1))
    db_session.commit()
    assert HoldService(uow_factory).expire_stale_holds() == 1
    assert HoldService(uow_factory).expire_stale_holds() == 0


# --- The worker loop ------------------------------------------------------------------------

def test_the_loop_runs_due_jobs_and_survives_a_crash(monkeypatch):
    calls = []

    def crashes(_):
        calls.append("crash")
        raise RuntimeError("boom")

    def works(_):
        calls.append("work")

    monkeypatch.setattr(worker, "JOBS", [("crash", crashes, 30), ("work", works, 30)])
    next_run: dict[str, float] = {}

    worker.run_due_jobs(None, next_run, now=100)  # first turn: both run, the crash is only logged
    assert calls == ["crash", "work"]

    worker.run_due_jobs(None, next_run, now=110)  # 10 s later: not their turn yet
    assert calls == ["crash", "work"]

    worker.run_due_jobs(None, next_run, now=130)  # 30 s later: both run again
    assert calls == ["crash", "work", "crash", "work"]
