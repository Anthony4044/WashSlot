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

from tests.conformance.contract import check, check_error
from tests.conformance.slots import find_free_slot
from tests.conformance.users import PASSWORD, unique_email

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
