"""GET /me/reservations and GET /reservations/{id}, judged by the contract.

Needs hold + confirm + browsing + seed data for the full flow. Until those exist it is skipped.
"""
import uuid

import pytest

from tests.conformance.contract import check, check_error
from tests.conformance.slots import find_free_slot
from tests.conformance.users import PASSWORD, unique_email

LIST, GET = "/me/reservations", "/reservations/{reservationId}"
UNKNOWN = "res_999999999"


def auth(customer) -> dict[str, str]:
    return {"Authorization": customer["Authorization"]}


def hold_then_confirm(api, customer, slot_id: str) -> str:
    r = api.post(
        f"/slots/{slot_id}/holds",
        json={"confirmationEmail": customer["email"]},
        headers={**auth(customer), "Idempotency-Key": str(uuid.uuid4())},
    )
    if r.status_code == 404:
        pytest.skip("POST /slots/{slotId}/holds is not there yet (US-4.1)")
    assert r.status_code == 201, r.text
    hold_id = r.json()["holdId"]
    confirmed = api.post(f"/holds/{hold_id}/confirm", headers=auth(customer))
    assert confirmed.status_code == 200, confirmed.text
    return confirmed.json()["reservationId"]


def test_list_empty_when_none(api, customer):
    r = api.get("/me/reservations", headers=auth(customer))
    assert r.status_code == 200
    assert check(r, LIST, "get")["reservations"] == []


def test_list_and_get_after_confirm(api, customer):
    reservation_id = hold_then_confirm(api, customer, find_free_slot(api))

    listing = api.get("/me/reservations", headers=auth(customer))
    assert listing.status_code == 200
    body = check(listing, LIST, "get")
    assert any(item["reservationId"] == reservation_id for item in body["reservations"])

    one = api.get(f"/reservations/{reservation_id}", headers=auth(customer))
    assert one.status_code == 200
    fetched = check(one, GET, "get")
    assert fetched["reservationId"] == reservation_id and fetched["status"] == "CONFIRMED"


def test_list_only_shows_own(api, customer):
    reservation_id = hold_then_confirm(api, customer, find_free_slot(api))
    stranger_email = unique_email()
    api.post("/auth/register", json={"email": stranger_email, "password": PASSWORD})
    token = api.post("/auth/login", json={"email": stranger_email, "password": PASSWORD}).json()["accessToken"]
    stranger = {"Authorization": f"Bearer {token}"}

    theirs = check(api.get("/me/reservations", headers=stranger), LIST, "get")
    assert all(item["reservationId"] != reservation_id for item in theirs["reservations"])


def test_someone_elses_reservation_is_404(api, customer):
    reservation_id = hold_then_confirm(api, customer, find_free_slot(api))
    stranger_email = unique_email()
    api.post("/auth/register", json={"email": stranger_email, "password": PASSWORD})
    token = api.post("/auth/login", json={"email": stranger_email, "password": PASSWORD}).json()["accessToken"]
    headers = {"Authorization": f"Bearer {token}"}
    check_error(api.get(f"/reservations/{reservation_id}", headers=headers), GET, "get", 404, "not_found")


def test_unknown_reservation_is_404(api, customer):
    check_error(api.get(f"/reservations/{UNKNOWN}", headers=auth(customer)), GET, "get", 404, "not_found")


def test_no_token_is_401(api):
    check_error(api.get("/me/reservations"), LIST, "get", 401, "missing_token")
    check_error(api.get(f"/reservations/{UNKNOWN}"), GET, "get", 401, "missing_token")
