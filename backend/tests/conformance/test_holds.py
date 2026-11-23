"""GET /holds/{holdId} and POST /holds/{holdId}/confirm, judged by the contract.

The full flow finds a free slot and holds it through the API, so it needs browsing (US-3.1),
placing a hold (US-4.1) and seeded laundromats. Until those exist it is skipped, and says why.
"""
import uuid
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime

import pytest

from tests.conformance.contract import check, check_error
from tests.conformance.slots import find_free_slot
from tests.conformance.users import PASSWORD, unique_email

GET, CONFIRM = "/holds/{holdId}", "/holds/{holdId}/confirm"
UNKNOWN = "hold_999999999"


def auth(customer) -> dict[str, str]:
    return {"Authorization": customer["Authorization"]}


def test_unknown_hold_is_404(api, customer):
    check_error(api.get(f"/holds/{UNKNOWN}", headers=auth(customer)), GET, "get", 404, "not_found")
    check_error(api.post(f"/holds/{UNKNOWN}/confirm", headers=auth(customer)), CONFIRM, "post", 404, "not_found")


def test_no_token_is_401(api):
    check_error(api.get(f"/holds/{UNKNOWN}"), GET, "get", 401, "missing_token")
    check_error(api.post(f"/holds/{UNKNOWN}/confirm"), CONFIRM, "post", 401, "missing_token")


def test_bad_token_is_401(api):
    bad = {"Authorization": "Bearer not.a.jwt"}
    check_error(api.post(f"/holds/{UNKNOWN}/confirm", headers=bad), CONFIRM, "post", 401, "invalid_token")


def place_hold(api, customer, slot_id: str) -> str:
    r = api.post(f"/slots/{slot_id}/holds", json={"confirmationEmail": customer["email"]},
                 headers={**auth(customer), "Idempotency-Key": str(uuid.uuid4())})
    if r.status_code == 404:
        pytest.skip("POST /slots/{slotId}/holds is not there yet (US-4.1)")
    assert r.status_code == 201, r.text
    return r.json()["holdId"]


def test_hold_then_confirm_then_confirm_again(api, customer):
    hold_id = place_hold(api, customer, find_free_slot(api))

    r = api.get(f"/holds/{hold_id}", headers=auth(customer))
    assert r.status_code == 200
    assert check(r, GET, "get")["status"] == "HELD"

    first = api.post(f"/holds/{hold_id}/confirm", headers=auth(customer))
    assert first.status_code == 200
    reservation = check(first, CONFIRM, "post")
    assert reservation["status"] == "CONFIRMED"
    assert reservation["reservationId"] == hold_id.replace("hold_", "res_")

    again = api.post(f"/holds/{hold_id}/confirm", headers=auth(customer))
    assert again.status_code == 200 and check(again, CONFIRM, "post") == reservation


def test_a_new_hold_lasts_ten_minutes_by_the_servers_clock(api, customer):
    """Expiry, from the outside (US-8.4). We can't wait 10 minutes here: tests/test_expiry.py moves a
    fake clock past expiresAt. This checks the window the contract promises, by the server's own clock."""
    r = api.post(f"/slots/{find_free_slot(api)}/holds", json={"confirmationEmail": customer["email"]},
                 headers={**auth(customer), "Idempotency-Key": str(uuid.uuid4())})
    assert r.status_code == 201, r.text
    hold = check(r, "/slots/{slotId}/holds", "post")

    left = datetime.fromisoformat(hold["expiresAt"]) - parsedate_to_datetime(r.headers["date"])
    assert timedelta(minutes=9, seconds=30) <= left <= timedelta(minutes=10, seconds=30), left

    again = api.get(f"/holds/{hold['holdId']}", headers=auth(customer))
    assert again.status_code == 200
    assert check(again, GET, "get") == hold  # still HELD, and the deadline doesn't move


def test_someone_elses_hold_is_404(api, customer):
    hold_id = place_hold(api, customer, find_free_slot(api))
    stranger = unique_email()
    api.post("/auth/register", json={"email": stranger, "password": PASSWORD})
    token = api.post("/auth/login", json={"email": stranger, "password": PASSWORD}).json()["accessToken"]
    headers = {"Authorization": f"Bearer {token}"}
    check_error(api.get(f"/holds/{hold_id}", headers=headers), GET, "get", 404, "not_found")
    check_error(api.post(f"/holds/{hold_id}/confirm", headers=headers), CONFIRM, "post", 404, "not_found")
