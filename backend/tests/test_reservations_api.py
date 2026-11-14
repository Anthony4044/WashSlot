"""GET /me/reservations and GET /reservations/{id} through HTTP (in-memory UoW + contract checks)."""
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_uow_factory
from app.data.memory import MemoryUnitOfWork
from app.domain.enums import ReservationStatus
from app.domain.slot import MachineSlot, Reservation
from app.main import app
from tests.conformance.contract import check, check_error

LIST, GET = "/me/reservations", "/reservations/{reservationId}"
ALICE, BOB = 1, 2


@pytest.fixture
def memory_client(api_client, memory_uow) -> Iterator[TestClient]:
    app.dependency_overrides[get_uow_factory] = lambda: memory_uow
    yield api_client
    app.dependency_overrides.pop(get_uow_factory, None)


def put_reservation(uow: MemoryUnitOfWork, user_id=ALICE, slot_id=1,
                    status=ReservationStatus.CONFIRMED) -> int:
    now = datetime.now(UTC)
    uow.slots.add(
        MachineSlot(id=slot_id, machine_id=4, start_time=now + timedelta(hours=2),
                    end_time=now + timedelta(hours=3))
    )
    slot = uow.slots.get(slot_id)
    slot.reservations.append(
        Reservation(
            id=None,
            slot_id=slot_id,
            user_id=user_id,
            status=status,
            confirmation_email="alice@example.com",
            expires_at=None if status != ReservationStatus.HELD else now + timedelta(minutes=10),
            confirmed_at=now if status == ReservationStatus.CONFIRMED else None,
        )
    )
    uow.slots.save(slot)
    return slot.reservations[0].id


def test_list_my_reservations(memory_client, memory_uow, bearer):
    put_reservation(memory_uow, user_id=ALICE, slot_id=1)
    put_reservation(memory_uow, user_id=BOB, slot_id=2)
    r = memory_client.get("/me/reservations", headers=bearer(ALICE))
    assert r.status_code == 200
    body = check(r, LIST, "get")
    assert len(body["reservations"]) == 1
    assert body["reservations"][0]["reservationId"].startswith("res_")


def test_list_newest_first(memory_client, memory_uow, bearer):
    older = put_reservation(memory_uow, user_id=ALICE, slot_id=1)
    newer = put_reservation(memory_uow, user_id=ALICE, slot_id=2)
    body = check(memory_client.get("/me/reservations", headers=bearer(ALICE)), LIST, "get")
    ids = [item["reservationId"] for item in body["reservations"]]
    assert ids == [f"res_{newer}", f"res_{older}"]


def test_list_needs_a_token(memory_client):
    check_error(memory_client.get("/me/reservations"), LIST, "get", 401, "missing_token")


def test_get_my_reservation(memory_client, memory_uow, bearer):
    reservation_id = put_reservation(memory_uow, user_id=ALICE)
    r = memory_client.get(f"/reservations/res_{reservation_id}", headers=bearer(ALICE))
    assert r.status_code == 200
    body = check(r, GET, "get")
    assert body["reservationId"] == f"res_{reservation_id}" and body["status"] == "CONFIRMED"


def test_get_someone_elses_reservation_is_404(memory_client, memory_uow, bearer):
    reservation_id = put_reservation(memory_uow, user_id=ALICE)
    # Customer B changes the id: still 404, never reveals that Alice's booking exists.
    check_error(
        memory_client.get(f"/reservations/res_{reservation_id}", headers=bearer(BOB)),
        GET,
        "get",
        404,
        "not_found",
    )


def test_get_needs_a_token(memory_client, memory_uow):
    reservation_id = put_reservation(memory_uow)
    check_error(memory_client.get(f"/reservations/res_{reservation_id}"), GET, "get", 401, "missing_token")


@pytest.mark.parametrize("bad_id", ["res_abc", "hold_1", "res_0", "1"])
def test_get_a_malformed_id_is_404(memory_client, bearer, bad_id):
    check_error(memory_client.get(f"/reservations/{bad_id}", headers=bearer(ALICE)), GET, "get", 404, "not_found")
