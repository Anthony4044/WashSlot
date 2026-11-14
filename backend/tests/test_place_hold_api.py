"""POST /slots/{slotId}/holds through HTTP, and every response checked against contract/openapi.yaml.

Most tests use the in-memory unit of work, so they run in CI without a database. They cover what
the interface layer decides: 201 · 401 · 403 · 404 · 409 · 422. The last tests use the real test
database (skipped without TEST_DATABASE_URL): the SQL repository, the database clock, and the
order of the writes (an expired hold is UPDATEd before the new one is INSERTed).

check(response, path, method) fails unless the contract documents that status for this operation
and the body matches its schema; check_error also pins the exact {"error": code}.
"""
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.api.deps import get_uow_factory
from app.data.tables import ReservationRow
from app.domain.enums import ReservationStatus
from app.domain.slot import MachineSlot
from app.main import app
from tests.conformance.contract import check, check_error
from tests.factories import make_reservation, make_slot, make_user

PLACE_HOLD = "/slots/{slotId}/holds"  # the operation's path in the contract
ALICE = 1
KEY = {"Idempotency-Key": "test-key-0001"}  # any 8 to 128 characters
BODY = {"confirmationEmail": "alice@example.com"}


@pytest.fixture
def memory_client(api_client, memory_uow) -> Iterator[TestClient]:
    """The API on an in-memory unit of work holding one free slot: slot_1, starting in an hour."""
    now = datetime.now(UTC)
    memory_uow.slots.add(MachineSlot(id=1, machine_id=4, start_time=now + timedelta(hours=1),
                                     end_time=now + timedelta(hours=2)))
    app.dependency_overrides[get_uow_factory] = lambda: memory_uow
    yield api_client
    app.dependency_overrides.pop(get_uow_factory, None)


def hold(client, slot_id="slot_1", headers=None, body=BODY):
    return client.post(f"/slots/{slot_id}/holds", json=body, headers=headers)


# --- 201: the hold ----------------------------------------------------------------------------

def test_hold_a_free_slot(memory_client, memory_uow, bearer):
    r = hold(memory_client, headers={**bearer(ALICE), **KEY})

    assert r.status_code == 201
    body = check(r, PLACE_HOLD, "post")  # matches the contract's Hold schema
    assert body["holdId"] == "hold_1"
    assert body["slotId"] == "slot_1"
    assert body["status"] == "HELD"
    assert body["confirmationEmail"] == "alice@example.com"
    # The hold belongs to whoever the TOKEN says (usr_1), never to anything in the body.
    assert memory_uow.slots.get(1).reservations[0].user_id == ALICE


def test_the_confirmation_email_is_trimmed(memory_client, bearer):
    r = hold(memory_client, headers={**bearer(ALICE), **KEY}, body={"confirmationEmail": "  alice@example.com "})
    assert check(r, PLACE_HOLD, "post")["confirmationEmail"] == "alice@example.com"


# --- 409: someone else got it -----------------------------------------------------------------

def test_a_taken_slot_is_409_slot_unavailable(memory_client, bearer):
    assert hold(memory_client, headers={**bearer(2), **KEY}).status_code == 201  # Bob holds it first
    r = hold(memory_client, headers={**bearer(ALICE), **KEY})
    check_error(r, PLACE_HOLD, "post", 409, "slot_unavailable")


# --- 404: no such slot ------------------------------------------------------------------------

def test_an_unknown_slot_is_404(memory_client, bearer):
    r = hold(memory_client, slot_id="slot_999", headers={**bearer(ALICE), **KEY})
    check_error(r, PLACE_HOLD, "post", 404, "not_found")


@pytest.mark.parametrize("bad_id", ["abc", "1", "slot_0", "slot_x", "lm_1", "hold_1"])
def test_a_malformed_slot_id_is_404_not_422(memory_client, bearer, bad_id):
    """The contract: a malformed or wrong-prefix id names nothing, so it is 404 not_found."""
    r = hold(memory_client, slot_id=bad_id, headers={**bearer(ALICE), **KEY})
    check_error(r, PLACE_HOLD, "post", 404, "not_found")


# --- 401 / 403: authentication and authorization (Ch. 8) --------------------------------------

def test_no_token_is_401_missing_token(memory_client):
    check_error(hold(memory_client, headers=KEY), PLACE_HOLD, "post", 401, "missing_token")


def test_a_bad_token_is_401_invalid_token(memory_client):
    r = hold(memory_client, headers={"Authorization": "Bearer not.a.jwt", **KEY})
    check_error(r, PLACE_HOLD, "post", 401, "invalid_token")


def test_a_token_without_reservations_write_is_403(memory_client, bearer):
    read_only = bearer(ALICE, scopes=("reservations:read",))  # a valid token, just not allowed to write
    check_error(hold(memory_client, headers={**read_only, **KEY}), PLACE_HOLD, "post", 403, "insufficient_scope")


# --- 422: the Idempotency-Key header (Ch. 3) --------------------------------------------------

@pytest.mark.parametrize("key", [None, "", "7-chars", "x" * 129], ids=["missing", "empty", "too-short", "too-long"])
def test_a_missing_or_bad_idempotency_key_is_422(memory_client, bearer, key):
    headers = bearer(ALICE) if key is None else {**bearer(ALICE), "Idempotency-Key": key}
    check_error(hold(memory_client, headers=headers), PLACE_HOLD, "post", 422, "idempotency_key_required")


@pytest.mark.parametrize("key", ["8-chars!", "x" * 128], ids=["8-chars", "128-chars"])  # shortest and longest allowed
def test_keys_of_8_and_128_characters_are_accepted(memory_client, bearer, key):
    assert hold(memory_client, headers={**bearer(ALICE), "Idempotency-Key": key}).status_code == 201


# --- 422: the body ----------------------------------------------------------------------------

@pytest.mark.parametrize("body", [
    {},  # confirmationEmail is required
    {"confirmationEmail": "not-an-email"},
    {"confirmationEmail": "alice@example.com", "userId": "usr_2"},  # strict: can't name another customer
])
def test_a_bad_body_is_422_invalid_request(memory_client, bearer, body):
    r = hold(memory_client, headers={**bearer(ALICE), **KEY}, body=body)
    check_error(r, PLACE_HOLD, "post", 422, "invalid_request")


# --- against Postgres (skipped without TEST_DATABASE_URL) -----------------------------------

def test_hold_on_the_database(client, db_session, bearer):
    user, slot = make_user(db_session), make_slot(db_session)
    db_session.commit()

    r = hold(client, slot_id=f"slot_{slot.id}", headers={**bearer(user.id), **KEY})

    body = check(r, PLACE_HOLD, "post")
    assert r.status_code == 201
    assert body["laundromatName"] == "Spin City"
    assert body["machineLabel"] == "Washer 4"
    row = db_session.scalars(select(ReservationRow)).one()
    assert (row.user_id, row.status) == (user.id, ReservationStatus.HELD)
    # expires_at = the DATABASE clock + 10 minutes. Compare with the database's own clock (not this
    # computer's), allowing for the moment that passed since the request.
    database_now = db_session.scalar(select(func.now()))
    assert timedelta(minutes=9) < row.expires_at - database_now <= timedelta(minutes=10)


def test_a_taken_slot_on_the_database_is_409(client, db_session, bearer):
    bob, alice, slot = make_user(db_session, "bob@example.com"), make_user(db_session), make_slot(db_session)
    make_reservation(db_session, bob, slot)  # Bob's live hold
    db_session.commit()

    r = hold(client, slot_id=f"slot_{slot.id}", headers={**bearer(alice.id), **KEY})
    check_error(r, PLACE_HOLD, "post", 409, "slot_unavailable")


def test_an_expired_hold_on_the_database_allows_a_new_hold(client, db_session, bearer):
    """Bob's hold ran out a second ago, but its row still says HELD (no background job has run).

    The partial unique index uq_reservations_active_slot still counts that row as active. So the
    service must UPDATE it to EXPIRED before it INSERTs Alice's hold, in the same transaction;
    otherwise the INSERT would hit the index. This test proves the order is right.
    """
    bob, alice, slot = make_user(db_session, "bob@example.com"), make_user(db_session), make_slot(db_session)
    stale = make_reservation(db_session, bob, slot, expires_at=datetime.now(UTC) - timedelta(seconds=1))
    db_session.commit()

    r = hold(client, slot_id=f"slot_{slot.id}", headers={**bearer(alice.id), **KEY})

    assert r.status_code == 201
    db_session.expire_all()  # forget what this session cached: read the rows fresh
    statuses = {row.user_id: row.status for row in db_session.scalars(select(ReservationRow))}
    assert statuses == {bob.id: ReservationStatus.EXPIRED, alice.id: ReservationStatus.HELD}
    assert db_session.get(ReservationRow, stale.id).status == ReservationStatus.EXPIRED
