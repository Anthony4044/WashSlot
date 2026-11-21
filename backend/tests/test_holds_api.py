"""GET /holds/{holdId} and POST /holds/{holdId}/confirm through HTTP.

Most tests use the in-memory unit of work, so they run in CI without a database. Every response
is also checked against contract/openapi.yaml. The last tests use the real test database
(skipped without TEST_DATABASE_URL): SQL repository, row lock and the database clock.
"""
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.deps import get_uow_factory
from app.data.memory import MemoryUnitOfWork
from app.data.tables import ReservationRow
from app.domain.enums import ReservationStatus
from app.domain.slot import MachineSlot, Reservation
from app.main import app
from tests.conformance.contract import check, check_error
from tests.factories import make_reservation, make_slot, make_user

GET, CONFIRM = "/holds/{holdId}", "/holds/{holdId}/confirm"
ALICE, BOB = 1, 2
READ_ONLY = ("reservations:read",)


@pytest.fixture
def memory_client(api_client, memory_uow) -> Iterator[TestClient]:
    app.dependency_overrides[get_uow_factory] = lambda: memory_uow
    yield api_client
    app.dependency_overrides.pop(get_uow_factory, None)


def put_hold(uow: MemoryUnitOfWork, user_id=ALICE, expires_in_min=10, status=ReservationStatus.HELD) -> int:
    now = datetime.now(UTC)
    uow.slots.add(MachineSlot(id=1, machine_id=4, start_time=now + timedelta(hours=2),
                              end_time=now + timedelta(hours=3)))
    slot = uow.slots.get(1)
    slot.reservations.append(Reservation(id=None, slot_id=1, user_id=user_id, status=status,
                                         confirmation_email="alice@example.com",
                                         expires_at=now + timedelta(minutes=expires_in_min)))
    uow.slots.save(slot)
    return slot.reservations[0].id


# --- GET /holds/{holdId} --------------------------------------------------------------------

def test_get_my_hold(memory_client, memory_uow, bearer):
    hold_id = put_hold(memory_uow)
    r = memory_client.get(f"/holds/hold_{hold_id}", headers=bearer(ALICE))
    assert r.status_code == 200
    body = check(r, GET, "get")
    assert body["holdId"] == f"hold_{hold_id}" and body["status"] == "HELD"


def test_get_needs_a_token(memory_client, memory_uow):
    hold_id = put_hold(memory_uow)
    check_error(memory_client.get(f"/holds/hold_{hold_id}"), GET, "get", 401, "missing_token")


def test_get_someone_elses_hold_is_404(memory_client, memory_uow, bearer):
    hold_id = put_hold(memory_uow, user_id=BOB)
    check_error(memory_client.get(f"/holds/hold_{hold_id}", headers=bearer(ALICE)), GET, "get", 404, "not_found")


@pytest.mark.parametrize("bad_id", ["hold_abc", "res_1", "hold_0", "1"])
def test_get_a_malformed_id_is_404(memory_client, bearer, bad_id):
    check_error(memory_client.get(f"/holds/{bad_id}", headers=bearer(ALICE)), GET, "get", 404, "not_found")


# --- POST /holds/{holdId}/confirm -----------------------------------------------------------

def test_confirm_my_hold(memory_client, memory_uow, bearer):
    hold_id = put_hold(memory_uow)
    r = memory_client.post(f"/holds/hold_{hold_id}/confirm", headers=bearer(ALICE))
    assert r.status_code == 200
    body = check(r, CONFIRM, "post")
    assert body["reservationId"] == f"res_{hold_id}" and body["status"] == "CONFIRMED"


def test_confirm_twice_is_200_with_the_same_body(memory_client, memory_uow, bearer):
    hold_id = put_hold(memory_uow)
    first = memory_client.post(f"/holds/hold_{hold_id}/confirm", headers=bearer(ALICE))
    again = memory_client.post(f"/holds/hold_{hold_id}/confirm", headers=bearer(ALICE))
    assert again.status_code == 200 and again.json() == first.json()


def test_confirm_an_expired_hold_is_409(memory_client, memory_uow, bearer):
    hold_id = put_hold(memory_uow, expires_in_min=-1)
    r = memory_client.post(f"/holds/hold_{hold_id}/confirm", headers=bearer(ALICE))
    check_error(r, CONFIRM, "post", 409, "hold_expired")


def test_confirm_a_cancelled_reservation_is_409(memory_client, memory_uow, bearer):
    hold_id = put_hold(memory_uow, status=ReservationStatus.CANCELLED)
    r = memory_client.post(f"/holds/hold_{hold_id}/confirm", headers=bearer(ALICE))
    check_error(r, CONFIRM, "post", 409, "already_cancelled")


def test_confirm_someone_elses_hold_is_404(memory_client, memory_uow, bearer):
    hold_id = put_hold(memory_uow, user_id=BOB)
    r = memory_client.post(f"/holds/hold_{hold_id}/confirm", headers=bearer(ALICE))
    check_error(r, CONFIRM, "post", 404, "not_found")


def test_confirm_needs_the_write_scope(memory_client, memory_uow, bearer):
    hold_id = put_hold(memory_uow)
    r = memory_client.post(f"/holds/hold_{hold_id}/confirm", headers=bearer(ALICE, scopes=READ_ONLY))
    check_error(r, CONFIRM, "post", 403, "insufficient_scope")


def test_confirm_with_a_bad_token_is_401(memory_client, memory_uow):
    hold_id = put_hold(memory_uow)
    r = memory_client.post(f"/holds/hold_{hold_id}/confirm", headers={"Authorization": "Bearer not.a.jwt"})
    check_error(r, CONFIRM, "post", 401, "invalid_token")


# --- against Postgres (skipped without TEST_DATABASE_URL) -----------------------------------

def test_confirm_on_the_database(client, db_session, bearer):
    user, slot = make_user(db_session), make_slot(db_session)
    hold = make_reservation(db_session, user, slot)
    db_session.commit()

    r = client.post(f"/holds/hold_{hold.id}/confirm", headers=bearer(user.id))
    body = check(r, CONFIRM, "post")
    assert r.status_code == 200 and body["laundromatName"] == "Spin City" and body["machineLabel"] == "Washer 4"

    db_session.expire_all()
    row = db_session.scalars(select(ReservationRow)).one()
    assert row.status == ReservationStatus.CONFIRMED and row.confirmed_at is not None

    again = client.post(f"/holds/hold_{hold.id}/confirm", headers=bearer(user.id))
    assert again.status_code == 200 and again.json() == r.json()


def test_the_database_clock_decides_expiry(client, db_session, bearer):
    user, slot = make_user(db_session), make_slot(db_session)
    hold = make_reservation(db_session, user, slot, expires_at=datetime.now(UTC) - timedelta(minutes=1))
    db_session.commit()

    r = client.post(f"/holds/hold_{hold.id}/confirm", headers=bearer(user.id))
    check_error(r, CONFIRM, "post", 409, "hold_expired")
    assert client.get(f"/holds/hold_{hold.id}", headers=bearer(user.id)).json()["status"] == "EXPIRED"
