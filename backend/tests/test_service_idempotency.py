"""US-5.2 in the service layer: HoldService.place_hold with an Idempotency-Key, on the in-memory unit of work.

What we prove (no HTTP, no database):
- a retry with the same key and the same request replays the first outcome, and holds only once
- the outcome is replayed WHATEVER it was: a refusal stays a refusal, even after the slot frees up
- the same key for another slot or another email is idempotency_key_reuse (a client bug)
- keys belong to their user, and a new key is a new attempt

Two copies arriving at the same moment (the twin path) need real transactions: that is
tests/test_hold_race.py, on the real database.
"""
from datetime import UTC, datetime, timedelta

import pytest

from app.data.memory import MemorySlotRepository, MemoryUnitOfWork
from app.domain.enums import ReservationStatus
from app.domain.slot import MachineSlot
from app.services.holds import HoldService

NOW = datetime(2030, 1, 7, 17, 0, tzinfo=UTC)  # any fixed time: the memory clock is ours
ALICE, BOB = 1, 2
SLOT, OTHER_SLOT = 1, 2
KEY = "attempt-0001"
EMAIL = "alice@example.com"


class Clock:
    def __init__(self):
        self.now = NOW

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def uow(clock) -> MemoryUnitOfWork:
    """Two free slots, starting in an hour."""
    uow = MemoryUnitOfWork(slots=MemorySlotRepository(clock=clock))
    for slot_id in (SLOT, OTHER_SLOT):
        uow.slots.add(MachineSlot(id=slot_id, machine_id=slot_id, start_time=NOW + timedelta(hours=1),
                                  end_time=NOW + timedelta(hours=2)))
    return uow


@pytest.fixture
def service(uow) -> HoldService:
    return HoldService(uow)


def holds_on(uow, slot_id: int = SLOT) -> list[tuple[int, ReservationStatus]]:
    return [(r.user_id, r.status) for r in uow.slots.get(slot_id).reservations]


# --- a retry replays -----------------------------------------------------------------------------

def test_a_retry_with_the_same_key_replays_the_hold_and_holds_only_once(service, uow):
    first = service.place_hold(ALICE, SLOT, EMAIL, KEY)
    retry = service.place_hold(ALICE, SLOT, EMAIL, KEY)  # the response was lost, so the client retries

    assert first.ok and not first.replayed
    assert retry.ok and retry.replayed
    assert retry.value == first.value  # the very same hold: same id, same expiry, same everything
    assert holds_on(uow) == [(ALICE, ReservationStatus.HELD)]  # and only one was ever written


def test_a_replay_is_the_stored_answer_not_a_fresh_look(service, clock):
    first = service.place_hold(ALICE, SLOT, EMAIL, KEY)
    clock.now += timedelta(minutes=30)  # the hold has expired by now

    retry = service.place_hold(ALICE, SLOT, EMAIL, KEY)

    assert retry.replayed
    assert retry.value == first.value  # still the original 201 body (status HELD), as the contract promises


def test_the_record_stores_the_body_exactly_as_it_was_sent(service, uow):
    first = service.place_hold(ALICE, SLOT, EMAIL, KEY)

    record = uow.idempotency.get(ALICE, KEY)
    assert record.endpoint == "placeHold"
    assert record.error_code is None
    assert record.response_body == first.value.model_dump(mode="json", by_alias=True)  # the wire body


# --- whatever it was ------------------------------------------------------------------------------

def test_a_replayed_refusal_stays_a_refusal_even_after_the_slot_frees_up(service, uow, clock):
    assert service.place_hold(BOB, SLOT, "bob@example.com", "bobs-attempt").ok
    refused = service.place_hold(ALICE, SLOT, EMAIL, KEY)
    assert refused.code == "slot_unavailable" and not refused.replayed

    clock.now += timedelta(minutes=10)  # Bob's hold expires: the slot is free again
    retry = service.place_hold(ALICE, SLOT, EMAIL, KEY)

    assert retry.code == "slot_unavailable"  # the same answer as the first time...
    assert retry.replayed
    assert holds_on(uow) == [(BOB, ReservationStatus.HELD)]  # ...and nothing was written for Alice
    assert service.place_hold(ALICE, SLOT, EMAIL, "a-new-attempt").ok  # a NEW key is a new attempt


def test_a_replayed_not_found(service):
    assert service.place_hold(ALICE, 999, EMAIL, KEY).code == "not_found"

    retry = service.place_hold(ALICE, 999, EMAIL, KEY)

    assert retry.code == "not_found"
    assert retry.replayed


# --- a key used for something else ----------------------------------------------------------------

@pytest.mark.parametrize(("slot_id", "email"), [(OTHER_SLOT, EMAIL), (SLOT, "someone.else@example.com")],
                         ids=["another-slot", "another-email"])
def test_the_same_key_for_a_different_request_is_reuse(service, uow, slot_id, email):
    assert service.place_hold(ALICE, SLOT, EMAIL, KEY).ok

    reused = service.place_hold(ALICE, slot_id, email, KEY)

    assert reused.code == "idempotency_key_reuse"
    assert not reused.replayed  # not a stored answer: a new error about this request
    assert holds_on(uow, OTHER_SLOT) == []  # nothing was held for the second request


def test_keys_belong_to_their_user(service, uow):
    """Bob happens to pick Alice's key: his request is his own attempt, never a replay of hers."""
    assert service.place_hold(ALICE, SLOT, EMAIL, KEY).ok

    bobs = service.place_hold(BOB, SLOT, "bob@example.com", KEY)

    assert bobs.code == "slot_unavailable"  # a real attempt, and Alice has the slot
    assert not bobs.replayed
    assert uow.idempotency.get(BOB, KEY).error_code == "slot_unavailable"
