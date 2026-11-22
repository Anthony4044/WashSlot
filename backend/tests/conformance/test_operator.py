"""The operator endpoints (US-7.1), judged by the contract alone.

Black-box: HTTP only, never `import app`. Access needs no data: no token is 401, and a customer
(registered through the API) gets 403 on every operator operation.

The operator's own calls need an operator account, and the API can't create one (registering always
makes a customer). So they log in as the seeded operator@example.com (scripts/seed_users.py and
seed_laundromats.py) and are skipped, saying why, when it isn't there.
"""
from datetime import date, timedelta

import pytest

from tests.conformance.contract import check, check_error

LAUNDROMATS = "/operator/laundromats"
MACHINES = "/operator/laundromats/{laundromatId}/machines"
MACHINE = "/operator/laundromats/{laundromatId}/machines/{machineId}"
SLOTS = "/operator/laundromats/{laundromatId}/slots"
DAY = (date.today() + timedelta(days=20)).isoformat()
SLOTS_BODY = {"fromDate": DAY, "toDate": DAY, "openTime": "23:00", "closeTime": "24:00", "slotMinutes": 60}

EVERY_OPERATION = [
    ("get", LAUNDROMATS, "/operator/laundromats", None),
    ("get", MACHINES, "/operator/laundromats/lm_1/machines", None),
    ("patch", MACHINE, "/operator/laundromats/lm_1/machines/mch_1", {"reservable": True}),
    ("post", SLOTS, "/operator/laundromats/lm_1/slots", SLOTS_BODY),
]
IDS = ["listOperatorLaundromats", "listOperatorMachines", "updateMachine", "createSlots"]


@pytest.fixture
def operator(api) -> dict[str, str]:
    """Headers for the seeded operator, or skip if the seed scripts haven't run on this database."""
    r = api.post("/auth/login", json={"email": "operator@example.com", "password": "operator123"})
    if r.status_code != 200:
        pytest.skip("no seeded operator@example.com: run scripts/seed_users.py and seed_laundromats.py")
    return {"Authorization": f"Bearer {r.json()['accessToken']}"}


@pytest.fixture
def my_laundromat(api, operator) -> str:
    laundromats = check(api.get(LAUNDROMATS, headers=operator), LAUNDROMATS, "get")["laundromats"]
    if not laundromats:
        pytest.skip("the seeded operator runs no laundromat: run scripts/seed_laundromats.py")
    return laundromats[0]["laundromatId"]


# --- access (no data needed) ---------------------------------------------------------------------------

@pytest.mark.parametrize(("method", "path", "url", "body"), EVERY_OPERATION, ids=IDS)
def test_no_token_is_401(api, method, path, url, body):
    check_error(api.request(method.upper(), url, json=body), path, method, 401, "missing_token")


@pytest.mark.parametrize(("method", "path", "url", "body"), EVERY_OPERATION, ids=IDS)
def test_a_customer_gets_403(api, customer, method, path, url, body):
    r = api.request(method.upper(), url, json=body, headers={"Authorization": customer["Authorization"]})
    check_error(r, path, method, 403, "insufficient_scope")


# --- the seeded operator ---------------------------------------------------------------------------------

def test_an_unknown_laundromat_is_404(api, operator):
    r = api.get("/operator/laundromats/lm_999999999/machines", headers=operator)
    check_error(r, MACHINES, "get", 404, "not_found")


def test_list_machines_and_set_one_to_what_it_already_is(api, operator, my_laundromat):
    machines = check(api.get(f"/operator/laundromats/{my_laundromat}/machines", headers=operator), MACHINES, "get")
    machine = machines["machines"][0]

    # Idempotent and harmless: setting the value it already has changes nothing.
    r = api.patch(f"/operator/laundromats/{my_laundromat}/machines/{machine['machineId']}",
                  json={"reservable": machine["reservable"]}, headers=operator)

    assert check(r, MACHINE, "patch") == machine


def test_create_slots_twice_creates_them_once(api, operator, my_laundromat):
    url = f"/operator/laundromats/{my_laundromat}/slots"

    first = check(api.post(url, json=SLOTS_BODY, headers=operator), SLOTS, "post")
    again = check(api.post(url, json=SLOTS_BODY, headers=operator), SLOTS, "post")

    assert again["created"] == 0  # whatever the first call made, the second makes nothing more
    assert again["skipped"] == first["created"] + first["skipped"]


def test_a_backwards_schedule_is_422(api, operator, my_laundromat):
    body = {**SLOTS_BODY, "openTime": "12:00", "closeTime": "08:00"}
    r = api.post(f"/operator/laundromats/{my_laundromat}/slots", json=body, headers=operator)
    check_error(r, SLOTS, "post", 422, "invalid_request")
