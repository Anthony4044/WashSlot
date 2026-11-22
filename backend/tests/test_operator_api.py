"""US-7.1 operator endpoints through HTTP, every response checked against contract/openapi.yaml.

Access first (T.7.1.3): no token is 401, a customer's token is 403, and the operator of laundromat 1
gets 404 for anything of laundromat 2, as if it did not exist. The first tests use the in-memory
unit of work (they run in CI); the last ones use the real test database (skipped without
TEST_DATABASE_URL): the switch and the slots are really saved, and a walk-in-only machine really
refuses a hold.
"""
from collections.abc import Iterator
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.api.deps import get_uow_factory
from app.data.tables import LaundromatRow, MachineRow, MachineSlotRow
from app.domain.enums import MachineType, UserRole
from app.domain.laundromat import Laundromat
from app.domain.machine import Machine
from app.domain.user import SCOPES_BY_ROLE
from app.main import app
from tests.conformance.contract import check, check_error
from tests.factories import TORONTO, make_slot, make_user

OPERATOR, OTHER_OPERATOR, CUSTOMER = 9, 8, 1
OPERATOR_SCOPES = SCOPES_BY_ROLE[UserRole.OPERATOR]
TOMORROW = (date.today() + timedelta(days=1)).isoformat()
SLOTS_BODY = {"fromDate": TOMORROW, "toDate": TOMORROW, "openTime": "08:00", "closeTime": "12:00", "slotMinutes": 60}

# (method, contract path, URL in laundromat 1, body)
LIST_LAUNDROMATS = ("get", "/operator/laundromats", "/operator/laundromats", None)
LIST_MACHINES = ("get", "/operator/laundromats/{laundromatId}/machines", "/operator/laundromats/lm_1/machines", None)
UPDATE_MACHINE = ("patch", "/operator/laundromats/{laundromatId}/machines/{machineId}",
                  "/operator/laundromats/lm_1/machines/mch_11", {"reservable": True})
CREATE_SLOTS = ("post", "/operator/laundromats/{laundromatId}/slots", "/operator/laundromats/lm_1/slots", SLOTS_BODY)
EVERY_OPERATION = [LIST_LAUNDROMATS, LIST_MACHINES, UPDATE_MACHINE, CREATE_SLOTS]
IDS = ["listOperatorLaundromats", "listOperatorMachines", "updateMachine", "createSlots"]


@pytest.fixture
def memory_client(api_client, memory_uow) -> Iterator[TestClient]:
    """Laundromat 1 (operator 9) with a washer that is walk-in only; laundromat 2 belongs to operator 8."""
    memory_uow.laundromats.add(Laundromat(1, "Spin City", "1 Main", "America/Toronto", operator_id=OPERATOR))
    memory_uow.laundromats.add(Laundromat(2, "Fresh Cycle", "2 Main", "America/Toronto", operator_id=OTHER_OPERATOR))
    memory_uow.machines.add(Machine(11, 1, "Washer 1", MachineType.WASHER, reservable=False))
    memory_uow.machines.add(Machine(21, 2, "Washer 1", MachineType.WASHER, reservable=True))
    app.dependency_overrides[get_uow_factory] = lambda: memory_uow
    yield api_client
    app.dependency_overrides.pop(get_uow_factory, None)


def call(client, method, url, body=None, headers=None):
    return client.request(method.upper(), url, json=body, headers=headers)


# --- who may call: 401 and 403 ------------------------------------------------------------------------

@pytest.mark.parametrize(("method", "path", "url", "body"), EVERY_OPERATION, ids=IDS)
def test_no_token_is_401(memory_client, method, path, url, body):
    check_error(call(memory_client, method, url, body), path, method, 401, "missing_token")


@pytest.mark.parametrize(("method", "path", "url", "body"), EVERY_OPERATION, ids=IDS)
def test_customers_get_403(memory_client, memory_uow, bearer, method, path, url, body):
    r = call(memory_client, method, url, body, bearer(CUSTOMER))  # a customer's token: no operator:manage

    check_error(r, path, method, 403, "insufficient_scope")
    assert memory_uow.machines.get(11).reservable is False  # nothing changed
    assert memory_uow.slots.all_slots() == []


# --- which laundromat: the operator of laundromat 1 can't touch laundromat 2 -----------------------

@pytest.mark.parametrize(("method", "path", "url", "body"), [
    (LIST_MACHINES[0], LIST_MACHINES[1], "/operator/laundromats/lm_2/machines", None),
    (UPDATE_MACHINE[0], UPDATE_MACHINE[1], "/operator/laundromats/lm_2/machines/mch_21", {"reservable": False}),
    (CREATE_SLOTS[0], CREATE_SLOTS[1], "/operator/laundromats/lm_2/slots", SLOTS_BODY),
    # laundromat 2's machine, reached through MY laundromat's URL:
    (UPDATE_MACHINE[0], UPDATE_MACHINE[1], "/operator/laundromats/lm_1/machines/mch_21", {"reservable": False}),
    (CREATE_SLOTS[0], CREATE_SLOTS[1], "/operator/laundromats/lm_1/slots", {**SLOTS_BODY, "machineIds": ["mch_21"]}),
], ids=["their-machines", "their-switch", "their-slots", "their-machine-via-mine", "their-machine-slots-via-mine"])
def test_the_operator_of_laundromat_1_cant_change_laundromat_2(memory_client, memory_uow, bearer,
                                                                method, path, url, body):
    r = call(memory_client, method, url, body, bearer(OPERATOR, OPERATOR_SCOPES))

    check_error(r, path, method, 404, "not_found")
    assert memory_uow.machines.get(21).reservable is True  # laundromat 2's washer is untouched
    assert memory_uow.slots.all_slots() == []


def test_an_operator_lists_only_their_own_laundromats(memory_client, bearer):
    r = call(memory_client, "get", "/operator/laundromats", headers=bearer(OPERATOR, OPERATOR_SCOPES))
    assert [lm["laundromatId"] for lm in check(r, LIST_LAUNDROMATS[1], "get")["laundromats"]] == ["lm_1"]


# --- what the operator can do ---------------------------------------------------------------------------

def test_switch_a_machine_on_and_list_it(memory_client, bearer):
    headers = bearer(OPERATOR, OPERATOR_SCOPES)

    updated = call(memory_client, "patch", "/operator/laundromats/lm_1/machines/mch_11", {"reservable": True}, headers)
    listed = call(memory_client, "get", "/operator/laundromats/lm_1/machines", headers=headers)

    assert check(updated, UPDATE_MACHINE[1], "patch") == {"machineId": "mch_11", "label": "Washer 1",
                                                         "type": "WASHER", "reservable": True}
    assert check(listed, LIST_MACHINES[1], "get")["machines"][0]["reservable"] is True


def test_create_slots_then_again_creates_nothing(memory_client, bearer):
    headers = bearer(OPERATOR, OPERATOR_SCOPES)
    body = {**SLOTS_BODY, "machineIds": ["mch_11"]}  # named, so the walk-in-only washer gets slots too

    first = call(memory_client, "post", "/operator/laundromats/lm_1/slots", body, headers)
    again = call(memory_client, "post", "/operator/laundromats/lm_1/slots", body, headers)

    assert check(first, CREATE_SLOTS[1], "post") == {"created": 4, "skipped": 0}
    assert check(again, CREATE_SLOTS[1], "post") == {"created": 0, "skipped": 4}


@pytest.mark.parametrize("body", [
    {**SLOTS_BODY, "openTime": "12:00", "closeTime": "08:00"},  # the domain's rules
    {**SLOTS_BODY, "toDate": (date.today() + timedelta(days=60)).isoformat()},
    {**SLOTS_BODY, "slotMinutes": 45},  # the contract's shapes
    {**SLOTS_BODY, "openTime": "8am"},
    {**SLOTS_BODY, "machineIds": []},
    {**SLOTS_BODY, "machineIds": ["mch_11", "mch_11"]},
    {**SLOTS_BODY, "laundromatId": "lm_2"},  # additionalProperties: false
], ids=["closes-before-opening", "too-many-days", "bad-length", "bad-time", "empty-machines", "repeated-machine",
        "unknown-field"])
def test_a_bad_slots_request_is_422(memory_client, memory_uow, bearer, body):
    r = call(memory_client, "post", "/operator/laundromats/lm_1/slots", body, bearer(OPERATOR, OPERATOR_SCOPES))
    check_error(r, CREATE_SLOTS[1], "post", 422, "invalid_request")
    assert memory_uow.slots.all_slots() == []


@pytest.mark.parametrize("body", [{"reservable": "yes"}, {"reservable": 1}, {}, {"reservable": True, "label": "x"}])
def test_a_bad_switch_request_is_422(memory_client, bearer, body):
    r = call(memory_client, "patch", UPDATE_MACHINE[2], body, bearer(OPERATOR, OPERATOR_SCOPES))
    check_error(r, UPDATE_MACHINE[1], "patch", 422, "invalid_request")


# --- on the database ----------------------------------------------------------------------------------

@pytest.fixture
def operated_slot(db_session):
    """A future slot on a reservable washer of a laundromat run by a real operator user."""
    operator = make_user(db_session, "operator@example.com")
    laundromat = LaundromatRow(name="Spin City", address="1 Main St", operator_id=operator.id)
    db_session.add(laundromat)
    db_session.flush()
    slot = make_slot(db_session, laundromat=laundromat)
    db_session.commit()
    return operator, laundromat, slot


def test_on_the_database_a_walk_in_only_machine_refuses_holds_and_leaves_the_grid(client, db_session, bearer,
                                                                                  operated_slot):
    operator, laundromat, slot = operated_slot
    customer = make_user(db_session, "kim@example.com")
    db_session.commit()

    switched = client.patch(f"/operator/laundromats/lm_{laundromat.id}/machines/mch_{slot.machine_id}",
                            json={"reservable": False}, headers=bearer(operator.id, OPERATOR_SCOPES))
    held = client.post(f"/slots/slot_{slot.id}/holds", json={"confirmationEmail": "kim@example.com"},
                       headers={**bearer(customer.id), "Idempotency-Key": "kim-attempt-0001"})
    day = slot.start_time.astimezone(TORONTO).date().isoformat()  # the grid asks for a Toronto day
    grid = client.get(f"/laundromats/lm_{laundromat.id}/slots", params={"date": day})

    assert switched.status_code == 200
    db_session.expire_all()
    assert db_session.get(MachineRow, slot.machine_id).reservable is False  # really saved
    check_error(held, "/slots/{slotId}/holds", "post", 409, "slot_unavailable")
    assert grid.json()["machines"] == []  # the browse read model agrees with the domain rule


def test_on_the_database_create_slots_inserts_once(client, db_session, bearer, operated_slot):
    operator, laundromat, slot = operated_slot
    url = f"/operator/laundromats/lm_{laundromat.id}/slots"
    body = {**SLOTS_BODY, "machineIds": [f"mch_{slot.machine_id}"]}

    first = client.post(url, json=body, headers=bearer(operator.id, OPERATOR_SCOPES))
    again = client.post(url, json=body, headers=bearer(operator.id, OPERATOR_SCOPES))

    assert first.json() == {"created": 4, "skipped": 0}
    assert again.json() == {"created": 0, "skipped": 4}  # ON CONFLICT (machine_id, start_time) DO NOTHING
    count = db_session.scalar(select(func.count()).select_from(MachineSlotRow)
                              .where(MachineSlotRow.machine_id == slot.machine_id))
    assert count == 1 + 4  # the factory's slot plus the four new ones
