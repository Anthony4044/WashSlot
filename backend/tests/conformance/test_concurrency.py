"""Concurrency, judged over HTTP (US-8.4): many clicks at the same moment, still one booking.

tests/test_hold_race.py proves the lock inside the server, on Postgres. These tests prove the same from
the outside, on any running server, by sending the requests at the same moment:
- ten customers hold one slot: one gets 201, the other nine get 409 slot_unavailable
- one customer sends the same hold eight times (one Idempotency-Key): one hold, the rest replay it
- confirming or cancelling the same booking four times at once gives four identical answers
"""
import uuid

from tests.conformance.contract import check, check_error
from tests.conformance.parallel import at_once
from tests.conformance.slots import find_free_slot
from tests.conformance.users import new_customer

PLACE_HOLD = "/slots/{slotId}/holds"
CONFIRM = "/holds/{holdId}/confirm"
RESERVATION = "/reservations/{reservationId}"
MINE = "/me/reservations"


def auth(customer) -> dict[str, str]:
    return {"Authorization": customer["Authorization"]}


def hold(api, customer, slot_id: str, key: str | None = None):
    return api.post(f"/slots/{slot_id}/holds", json={"confirmationEmail": customer["email"]},
                    headers={**auth(customer), "Idempotency-Key": key or str(uuid.uuid4())})


def test_ten_customers_hold_the_same_slot_at_the_same_moment(api):
    slot_id = find_free_slot(api)
    customers = [new_customer(api) for _ in range(10)]

    responses = at_once(10, lambda i: hold(api, customers[i], slot_id))

    statuses = sorted(r.status_code for r in responses)
    assert statuses == [201] + [409] * 9, statuses  # exactly one winner, never a double booking
    for r in responses:
        if r.status_code == 201:
            assert check(r, PLACE_HOLD, "post")["status"] == "HELD"
        else:
            check_error(r, PLACE_HOLD, "post", 409, "slot_unavailable")


def test_one_customer_sends_the_same_hold_eight_times_at_once(api, customer):
    slot_id = find_free_slot(api)
    key = str(uuid.uuid4())  # one attempt, sent eight times (a double click, or a client retrying early)

    responses = at_once(8, lambda _: hold(api, customer, slot_id, key))

    assert [r.status_code for r in responses] == [201] * 8  # nobody sees a 409 for their own hold
    holds = [check(r, PLACE_HOLD, "post") for r in responses]
    assert len({h["holdId"] for h in holds}) == 1  # all eight answers are the same hold
    assert sum(r.headers.get("Idempotency-Replayed") == "true" for r in responses) == 7
    mine = check(api.get(MINE, headers=auth(customer)), MINE, "get")["reservations"]
    assert [r["slotId"] for r in mine] == [slot_id]  # and the slot was held once


def test_confirming_the_same_hold_four_times_at_once_books_it_once(api, customer):
    r = hold(api, customer, find_free_slot(api))
    assert r.status_code == 201, r.text
    hold_id = r.json()["holdId"]

    responses = at_once(4, lambda _: api.post(f"/holds/{hold_id}/confirm", headers=auth(customer)))

    assert [r.status_code for r in responses] == [200] * 4
    reservations = [check(r, CONFIRM, "post") for r in responses]
    assert all(r == reservations[0] for r in reservations)  # the same reservation, unchanged
    assert reservations[0]["status"] == "CONFIRMED"
    mine = check(api.get(MINE, headers=auth(customer)), MINE, "get")["reservations"]
    assert len(mine) == 1


def test_cancelling_the_same_booking_four_times_at_once(api, customer):
    r = hold(api, customer, find_free_slot(api))
    assert r.status_code == 201, r.text
    confirmed = api.post(f"/holds/{r.json()['holdId']}/confirm", headers=auth(customer))
    reservation_id = check(confirmed, CONFIRM, "post")["reservationId"]

    responses = at_once(4, lambda _: api.delete(f"/reservations/{reservation_id}", headers=auth(customer)))

    assert [r.status_code for r in responses] == [204] * 4  # cancelling is idempotent, even at once
    for r in responses:
        check(r, RESERVATION, "delete")
    after = api.get(f"/reservations/{reservation_id}", headers=auth(customer))
    assert check(after, RESERVATION, "get")["status"] == "CANCELLED"
