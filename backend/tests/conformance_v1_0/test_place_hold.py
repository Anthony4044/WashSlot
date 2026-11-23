"""POST /slots/{slotId}/holds, judged by the contract alone (lecture Ch. 2).

Black-box: these tests talk HTTP to a running server and never import `app`. check() fails unless the
contract documents the status for this operation and the body matches the schema; check_error()
also pins the exact {"error": code}.

The error cases need no data. The success case (201, then 409 for the next customer) needs a real
free slot, found by browsing the API, so it is skipped until US-3.1 and the seed scripts exist.
(A token without reservations:write -> 403 can't be made through the API: every customer's login
token has that scope. tests/test_place_hold_api.py covers 403.)
"""
import uuid

import pytest

from tests.conformance_v1_0.contract import check, check_error
from tests.conformance_v1_0.slots import find_free_slot
from tests.conformance_v1_0.users import PASSWORD, unique_email

PLACE_HOLD = "/slots/{slotId}/holds"
UNKNOWN = "slot_999999999"


def new_key() -> dict[str, str]:
    """A fresh Idempotency-Key: one per attempt, as the contract asks (a UUID is 36 characters)."""
    return {"Idempotency-Key": str(uuid.uuid4())}


def as_customer(customer) -> dict[str, str]:
    return {"Authorization": customer["Authorization"], **new_key()}


def hold(api, slot_id: str, headers: dict, body: dict | None = None):
    return api.post(f"/slots/{slot_id}/holds", json=body or {"confirmationEmail": "me@example.com"}, headers=headers)


def another_customer(api) -> dict[str, str]:
    """Register and log in a second customer through the API. Returns its headers."""
    email = unique_email()
    api.post("/auth/register", json={"email": email, "password": PASSWORD})
    token = api.post("/auth/login", json={"email": email, "password": PASSWORD}).json()["accessToken"]
    return {"Authorization": f"Bearer {token}", **new_key()}


# --- errors (no data needed) ------------------------------------------------------------------

def test_no_token_is_401_missing_token(api):
    check_error(hold(api, UNKNOWN, new_key()), PLACE_HOLD, "post", 401, "missing_token")


def test_a_bad_token_is_401_invalid_token(api):
    headers = {"Authorization": "Bearer not.a.jwt", **new_key()}
    check_error(hold(api, UNKNOWN, headers), PLACE_HOLD, "post", 401, "invalid_token")


def test_an_unknown_slot_is_404(api, customer):
    check_error(hold(api, UNKNOWN, as_customer(customer)), PLACE_HOLD, "post", 404, "not_found")


@pytest.mark.parametrize("bad_id", ["abc", "slot_0", "lm_1"])
def test_a_malformed_slot_id_is_404(api, customer, bad_id):
    check_error(hold(api, bad_id, as_customer(customer)), PLACE_HOLD, "post", 404, "not_found")


@pytest.mark.parametrize("key", [None, "7-chars", "x" * 129], ids=["missing", "too-short", "too-long"])
def test_a_missing_or_bad_idempotency_key_is_422(api, customer, key):
    headers = {"Authorization": customer["Authorization"]}
    if key is not None:
        headers["Idempotency-Key"] = key
    check_error(hold(api, UNKNOWN, headers), PLACE_HOLD, "post", 422, "idempotency_key_required")


@pytest.mark.parametrize("body", [
    {"confirmationEmail": "not-an-email"},  # contract: format: email
    {"confirmationEmail": "me@example.com", "userId": "usr_1"},  # contract: additionalProperties: false
])
def test_a_bad_body_is_422_invalid_request(api, customer, body):
    check_error(hold(api, UNKNOWN, as_customer(customer), body), PLACE_HOLD, "post", 422, "invalid_request")


# --- safe retries: the same Idempotency-Key again (US-5.2) -------------------------------------

def test_a_retry_with_the_same_key_replays_the_404(api, customer):
    headers = as_customer(customer)  # one key, used for both tries
    check_error(hold(api, UNKNOWN, headers), PLACE_HOLD, "post", 404, "not_found")

    retry = hold(api, UNKNOWN, headers)

    check_error(retry, PLACE_HOLD, "post", 404, "not_found")  # check() also allows the header here
    assert retry.headers["Idempotency-Replayed"] == "true"


def test_the_same_key_with_another_body_is_422_reuse(api, customer):
    headers = as_customer(customer)
    hold(api, UNKNOWN, headers, {"confirmationEmail": "me@example.com"})

    reused = hold(api, UNKNOWN, headers, {"confirmationEmail": "someone.else@example.com"})

    check_error(reused, PLACE_HOLD, "post", 422, "idempotency_key_reuse")


def test_a_retry_of_a_hold_replays_it_instead_of_holding_twice(api, customer):
    slot_id = find_free_slot(api)
    headers, body = as_customer(customer), {"confirmationEmail": customer["email"]}

    first = hold(api, slot_id, headers, body)
    retry = hold(api, slot_id, headers, body)  # as if the first response had been lost

    assert (first.status_code, retry.status_code) == (201, 201)
    assert check(retry, PLACE_HOLD, "post") == check(first, PLACE_HOLD, "post")  # the very same hold
    assert retry.headers["Idempotency-Replayed"] == "true"
    assert "Idempotency-Replayed" not in first.headers


# --- success, then the next customer is refused (needs US-3.1 and seeded slots) ---------------

def test_hold_a_free_slot_then_the_next_customer_gets_409(api, customer):
    slot_id = find_free_slot(api)

    first = hold(api, slot_id, as_customer(customer), {"confirmationEmail": customer["email"]})
    assert first.status_code == 201
    body = check(first, PLACE_HOLD, "post")
    assert body["slotId"] == slot_id
    assert body["status"] == "HELD"

    second = hold(api, slot_id, another_customer(api))
    check_error(second, PLACE_HOLD, "post", 409, "slot_unavailable")
