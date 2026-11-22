"""The race test (lecture Ch. 7): many customers click "Hold" on the same slot at the same moment.

It runs against the real test database (skipped without TEST_DATABASE_URL), because what it tests is
a real Postgres row lock (SELECT ... FOR UPDATE). An in-memory double can't prove anything here.

How the race is made: Listing 7.3's pattern. Each customer runs in its own thread, and a
threading.Barrier holds every thread at the starting line until all of them are ready. Then they all
go at once, so their transactions really overlap.

Two tests, like the lecture's demo (race.py "pessimistic" vs "unsafe"):
1. With the lock (the real code): exactly one 201, everyone else 409 slot_unavailable, one row.
2. Lock switched off (control group): the data is still safe, thanks to the database's partial unique
   index, but the losers crash with a database error instead of getting a clean 409.
   The constraint is the safety net; the lock is what makes the answers right.
"""
import threading

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import get_uow_factory
from app.data.database import make_session_factory
from app.data.repositories import SqlSlotRepository
from app.data.tables import ReservationRow
from app.data.unit_of_work import SqlAlchemyUnitOfWork
from app.domain.enums import ReservationStatus
from app.main import app
from app.services.holds import HoldService
from app.services.outcome import Outcome
from tests.factories import make_slot, make_user

N = 20  # customers racing for one slot


def race(n: int, attempt) -> list:
    """Start n threads, hold them at a Barrier, release them together. Returns what each attempt returned
    (or the exception it raised), in the order they finished."""
    start_line = threading.Barrier(n)
    results = []

    def run(i: int):
        start_line.wait()  # wait here until all n threads are ready...
        try:
            results.append(attempt(i))  # ...then everyone goes at the same moment
        except Exception as crash:  # the control test expects some crashes; keep them to look at
            results.append(crash)

    threads = [threading.Thread(target=run, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results


@pytest.fixture
def racing_uow_factory(db_engine):
    """Units of work on a connection pool with one connection ALREADY OPEN for every racer.

    Why: opening a new connection to Neon takes a few hundred milliseconds, and the times vary. With a
    cold pool the racers reach the database one by one, never really overlap, and the test proves
    nothing. (We checked: with the lock switched off it still passed.) With a warm connection each,
    all N transactions start within milliseconds of each other, so the race really happens.
    """
    engine = create_engine(db_engine.url, pool_size=N, max_overflow=0)
    for connection in race(N, lambda i: engine.connect()):  # open N connections at the same time...
        connection.close()  # ...and hand them back to the pool, still open
    session_factory = make_session_factory(engine)
    yield lambda: SqlAlchemyUnitOfWork(session_factory)
    engine.dispose()


@pytest.fixture
def racing_client(api_client, racing_uow_factory):
    """The API, wired to the warm pool above (and to the test key pair, through api_client)."""
    app.dependency_overrides[get_uow_factory] = lambda: racing_uow_factory
    yield api_client
    app.dependency_overrides.pop(get_uow_factory, None)


def make_customers(db_session, n: int) -> list[tuple[int, str]]:
    """n users in the database, as (id, email). Committed, because every request uses its own connection."""
    users = [make_user(db_session, f"customer{i}@example.com") for i in range(n)]
    db_session.commit()
    return [(u.id, u.email) for u in users]


def rows_for(db_session, slot_id: int) -> list[ReservationRow]:
    return db_session.scalars(select(ReservationRow).where(ReservationRow.slot_id == slot_id)).all()


# --- 1. the real code: pessimistic locking ------------------------------------------------------

def test_twenty_customers_click_hold_on_the_same_slot_at_once(racing_client, db_session, bearer):
    slot = make_slot(db_session)
    customers = make_customers(db_session, N)

    def click_hold(i: int):
        user_id, email = customers[i]
        headers = {**bearer(user_id), "Idempotency-Key": f"race-attempt-{i:02d}"}  # one attempt per customer
        return racing_client.post(f"/slots/slot_{slot.id}/holds", json={"confirmationEmail": email}, headers=headers)

    responses = race(N, click_hold)

    # No request crashed. (Remove lock=True in HoldService.place_hold and this is what fails: the
    # racers' INSERTs collide on the unique index and the server errors out.)
    crashed = [r for r in responses if isinstance(r, Exception)]
    assert not crashed, f"{len(crashed)} requests crashed, e.g. {crashed[0]!r}"

    # Exactly one winner; the 19 others were told the truth: someone else got it.
    assert sorted(r.status_code for r in responses) == [201] + [409] * (N - 1)
    assert all(r.json() == {"error": "slot_unavailable"} for r in responses if r.status_code == 409)

    # And the database agrees: one row for this slot, the winner's HELD hold. The losers wrote nothing.
    rows = rows_for(db_session, slot.id)
    assert len(rows) == 1
    assert rows[0].status == ReservationStatus.HELD
    winner = next(r for r in responses if r.status_code == 201)
    assert winner.json()["holdId"] == f"hold_{rows[0].id}"


# --- 2. control group: the same race with the lock switched off -------------------------------

def test_without_the_lock_only_the_unique_index_prevents_a_double_booking(racing_uow_factory, db_session,
                                                                          monkeypatch):
    """What if we forgot `lock=True`? Every thread reads the slot at the same moment, all see it free,
    and all try to INSERT a hold: the check-then-act race.

    The partial unique index uq_reservations_active_slot (migration 001: one HELD/CONFIRMED row per slot)
    lets only one INSERT through. The others fail with IntegrityError, which a customer would see as a
    500 internal_error. So the data is safe but the answers are wrong. That is why we lock.
    """
    real_get = SqlSlotRepository.get
    monkeypatch.setattr(SqlSlotRepository, "get",
                        lambda self, slot_id, *, lock=False: real_get(self, slot_id, lock=False))  # no FOR UPDATE

    slot = make_slot(db_session)
    customers = make_customers(db_session, N)
    service = HoldService(racing_uow_factory)

    def place_hold(i: int):
        user_id, email = customers[i]
        return service.place_hold(user_id, slot.id, email, f"control-attempt-{i:02d}")  # one attempt each

    results = race(N, place_hold)

    holds = [r for r in results if isinstance(r, Outcome) and r.ok]
    crashes = [r for r in results if isinstance(r, IntegrityError)]
    refused = [r for r in results if isinstance(r, Outcome) and r.code == "slot_unavailable"]
    assert len(holds) == 1  # still never two holds: the index refused every other INSERT
    assert crashes, "without the lock, some requests should pass the check together and crash on the index"
    assert len(holds) + len(crashes) + len(refused) == N  # nothing else happened

    assert [r.status for r in rows_for(db_session, slot.id)] == [ReservationStatus.HELD]  # one row in the database
