"""US-7.2 over HTTP against the authored contract. Seed the demo users and laundromats first."""
from tests.conformance_v1_0.contract import check, check_error
from tests.conformance_v1_0.slots import find_free_slot
from tests.conformance_v1_0.test_reservations import auth, hold_then_confirm

CHECK_IN = "/reservations/{reservationId}/check-in"
LOCATIONS = "/operator/laundromats"
TODAY = "/operator/laundromats/{laundromatId}/today"


def check_in_path(reservation_id):
    return CHECK_IN.format(reservationId=reservation_id)


def test_customer_check_in_returns_the_same_reservation_on_retry(api, customer):
    reservation_id = hold_then_confirm(api, customer, find_free_slot(api))
    path = check_in_path(reservation_id)
    first = api.post(path, headers=auth(customer))
    assert first.status_code == 200
    body = check(first, CHECK_IN, "post")
    assert body["reservationId"] == reservation_id
    assert body["status"] == "CONFIRMED"
    assert body["checkedInAt"] is not None
    again = api.post(path, headers=auth(customer))
    assert again.status_code == 200
    assert check(again, CHECK_IN, "post") == body


def test_cancelled_reservation_cannot_check_in(api, customer):
    reservation_id = hold_then_confirm(api, customer, find_free_slot(api))
    headers = auth(customer)
    assert api.delete(f"/reservations/{reservation_id}", headers=headers).status_code == 204
    response = api.post(check_in_path(reservation_id), headers=headers)
    check_error(response, CHECK_IN, "post", 409, "already_cancelled")


def test_unknown_reservation_and_missing_token(api, customer):
    path = check_in_path("res_999999999")
    check_error(api.post(path), CHECK_IN, "post", 401, "missing_token")
    check_error(api.post(path, headers=auth(customer)), CHECK_IN, "post", 404, "not_found")


def test_customer_cannot_read_operator_routes(api, customer):
    for path, contract_path in ((LOCATIONS, LOCATIONS), (TODAY.format(laundromatId="lm_1"), TODAY)):
        check_error(api.get(path), contract_path, "get", 401, "missing_token")
        check_error(api.get(path, headers=auth(customer)), contract_path, "get", 403, "insufficient_scope")


def test_operator_can_read_today_for_assigned_laundromats(api):
    login = api.post("/auth/login", json={"email": "operator@example.com", "password": "operator123"})
    assert login.status_code == 200, "Run the demo seed scripts before running live conformance tests."
    headers = {"Authorization": f"Bearer {login.json()['accessToken']}"}
    response = api.get(LOCATIONS, headers=headers)
    assert response.status_code == 200
    locations = check(response, LOCATIONS, "get")["laundromats"]
    assert locations, "The demo operator must be assigned to at least one laundromat."
    path = TODAY.format(laundromatId=locations[0]["laundromatId"])
    today = api.get(path, headers=headers)
    assert today.status_code == 200
    check(today, TODAY, "get")
    unknown = api.get(TODAY.format(laundromatId="lm_999999999"), headers=headers)
    check_error(unknown, TODAY, "get", 404, "not_found")
