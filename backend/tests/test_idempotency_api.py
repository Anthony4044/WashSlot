"""US-5.2 through HTTP: POST /slots/{slotId}/holds retried with the same Idempotency-Key.

Every response is checked against contract/openapi.yaml, including that Idempotency-Replayed is
only sent where the contract documents it. The first tests use the in-memory unit of work (they run
in CI); the last ones use the real test database (skipped without TEST_DATABASE_URL) to check what
was really committed: one reservation row and one idempotency record.

The race (8 copies of one request at the same moment) is in tests/test_hold_race.py.
"""
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.deps import get_uow_factory
from app.data.tables import IdempotencyRecordRow, ReservationRow
from app.domain.enums import ReservationStatus
from app.domain.slot import MachineSlot
from app.main import app
from tests.conformance.contract import check, check_error
from tests.factories import make_reservation, make_slot, make_user

PLACE_HOLD = "/slots/{slotId}/holds"
ALICE, BOB = 1, 2
KEY = "retry-me-0001"
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


def hold(client, headers, slot_id="slot_1", key=KEY, body=BODY):
    return client.post(f"/slots/{slot_id}/holds", json=body, headers={**headers, "Idempotency-Key": key})


# --- in memory: what the client sees ----------------------------------------------------------------

def test_a_retry_gets_the_same_201_marked_as_replayed(memory_client, memory_uow, bearer):
    first = hold(memory_client, bearer(ALICE))
    retry = hold(memory_client, bearer(ALICE))

    assert first.status_code == retry.status_code == 201
    assert "Idempotency-Replayed" not in first.headers  # the first answer is not a replay
    assert retry.headers["Idempotency-Replayed"] == "true"
    assert check(retry, PLACE_HOLD, "post") == check(first, PLACE_HOLD, "post")  # byte-for-byte the same hold
    assert len(memory_uow.slots.get(1).reservations) == 1  # and the slot was held once


def test_a_replayed_409_stays_409(memory_client, bearer):
    hold(memory_client, bearer(BOB), key="bobs-attempt")  # Bob takes the slot first
    hold(memory_client, bearer(ALICE))  # Alice: 409

    retry = hold(memory_client, bearer(ALICE))

    check_error(retry, PLACE_HOLD, "post", 409, "slot_unavailable")
    assert retry.headers["Idempotency-Replayed"] == "true"


def test_a_replayed_404_stays_404(memory_client, bearer):
    hold(memory_client, bearer(ALICE), slot_id="slot_999")

    retry = hold(memory_client, bearer(ALICE), slot_id="slot_999")

    check_error(retry, PLACE_HOLD, "post", 404, "not_found")
    assert retry.headers["Idempotency-Replayed"] == "true"


@pytest.mark.parametrize(("slot_id", "body"), [
    ("slot_999", BODY),
    ("slot_1", {"confirmationEmail": "someone.else@example.com"}),
], ids=["another-slot", "another-body"])
def test_the_same_key_with_a_different_request_is_422_reuse(memory_client, bearer, slot_id, body):
    assert hold(memory_client, bearer(ALICE)).status_code == 201

    reused = hold(memory_client, bearer(ALICE), slot_id=slot_id, body=body)

    check_error(reused, PLACE_HOLD, "post", 422, "idempotency_key_reuse")
    assert "Idempotency-Replayed" not in reused.headers


def test_a_trimmed_email_is_the_same_request(memory_client, bearer):
    """The body is compared as the server understood it: " alice@example.com " IS alice@example.com."""
    first = hold(memory_client, bearer(ALICE))
    retry = hold(memory_client, bearer(ALICE), body={"confirmationEmail": " alice@example.com "})

    assert retry.status_code == 201
    assert retry.json()["holdId"] == first.json()["holdId"]


# --- on the database: what was committed ----------------------------------------------------------

def test_a_retry_on_the_database_writes_one_hold_and_one_record(client, db_session, bearer):
    user, slot = make_user(db_session, "alice@example.com"), make_slot(db_session)
    db_session.commit()

    first = hold(client, bearer(user.id), slot_id=f"slot_{slot.id}")
    retry = hold(client, bearer(user.id), slot_id=f"slot_{slot.id}")

    assert (first.status_code, retry.status_code) == (201, 201)
    assert retry.headers["Idempotency-Replayed"] == "true"
    assert retry.json() == first.json()
    rows = db_session.scalars(select(ReservationRow).where(ReservationRow.slot_id == slot.id)).all()
    assert [r.status for r in rows] == [ReservationStatus.HELD]
    record = db_session.get(IdempotencyRecordRow, (user.id, KEY))
    assert record.endpoint == "placeHold"
    assert record.error_code is None
    assert record.response_body == first.json()  # stored exactly as it went on the wire


def test_a_refusal_is_committed_without_anything_else(client, db_session, bearer):
    """A 409 writes no reservation, but its record IS committed, so a retry gets the same 409."""
    bob, alice, slot = make_user(db_session, "bob@example.com"), make_user(db_session), make_slot(db_session)
    make_reservation(db_session, bob, slot)  # Bob holds the slot
    db_session.commit()

    refused = hold(client, bearer(alice.id), slot_id=f"slot_{slot.id}")

    assert refused.status_code == 409
    record = db_session.get(IdempotencyRecordRow, (alice.id, KEY))
    assert record.error_code == "slot_unavailable"
    assert record.response_body is None
    rows = db_session.scalars(select(ReservationRow).where(ReservationRow.slot_id == slot.id)).all()
    assert [r.user_id for r in rows] == [bob.id]
