"""The outbox, judged over HTTP (US-8.4): a confirmed booking owes its customer exactly one email.

Confirm writes the email in the same transaction as the reservation (US-6.1). From the outside, the
operator's Emails list shows it (US-7.3): one entry per booking, even when the customer confirms again
or four times at once, and none for a hold that was never confirmed. It is PENDING or SENT depending
on whether a worker runs, so both pass. These tests only read the list: they never retry an email.
"""
import uuid
from datetime import datetime

import pytest

from tests.conformance.contract import check
from tests.conformance.parallel import at_once
from tests.conformance.slots import find_free_slot

EMAILS = "/operator/notifications"
CONFIRM = "/holds/{holdId}/confirm"


def auth(customer) -> dict[str, str]:
    return {"Authorization": customer["Authorization"]}


@pytest.fixture
def slot_id(api, operator) -> str:
    """A free slot in a laundromat the seeded operator runs, so its email shows on their list."""
    laundromats = check(api.get("/operator/laundromats", headers=operator), "/operator/laundromats", "get")
    mine = {lm["laundromatId"] for lm in laundromats["laundromats"]}
    if not mine:
        pytest.skip("the seeded operator runs no laundromat: run scripts/seed_laundromats.py")
    return find_free_slot(api, mine)


def place_hold(api, customer, slot_id: str) -> str:
    r = api.post(f"/slots/{slot_id}/holds", json={"confirmationEmail": customer["email"]},
                 headers={**auth(customer), "Idempotency-Key": str(uuid.uuid4())})
    assert r.status_code == 201, r.text
    return r.json()["holdId"]


def emails_for(api, operator, reservation_id: str) -> list[dict]:
    listed = check(api.get(EMAILS, headers=operator), EMAILS, "get")["notifications"]  # newest 100
    return [email for email in listed if email["reservationId"] == reservation_id]


def test_a_confirmed_booking_queues_one_email_even_when_confirmed_again(api, operator, customer, slot_id):
    hold_id = place_hold(api, customer, slot_id)
    reservation = check(api.post(f"/holds/{hold_id}/confirm", headers=auth(customer)), CONFIRM, "post")
    api.post(f"/holds/{hold_id}/confirm", headers=auth(customer))  # a retry must not queue a second email

    [email] = emails_for(api, operator, reservation["reservationId"])

    assert email["status"] in {"PENDING", "SENT"}  # SENT once a worker has run
    assert email["recipient"] == reservation["confirmationEmail"] == customer["email"]
    assert (email["laundromatId"], email["machineLabel"]) == (reservation["laundromatId"], reservation["machineLabel"])
    assert datetime.fromisoformat(email["startTime"]) == datetime.fromisoformat(reservation["startTime"])


def test_four_confirms_at_once_queue_one_email(api, operator, customer, slot_id):
    hold_id = place_hold(api, customer, slot_id)

    responses = at_once(4, lambda _: api.post(f"/holds/{hold_id}/confirm", headers=auth(customer)))

    assert [r.status_code for r in responses] == [200] * 4
    reservation_id = responses[0].json()["reservationId"]
    assert len(emails_for(api, operator, reservation_id)) == 1


def test_a_hold_that_is_never_confirmed_queues_no_email(api, operator, customer, slot_id):
    hold_id = place_hold(api, customer, slot_id)

    assert emails_for(api, operator, hold_id.replace("hold_", "res_")) == []  # a hold keeps its number
