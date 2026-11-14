"""US-3.1: browse availability read model and API.

Pins the SQL read model to MachineSlot.is_available, and checks the public endpoints.
"""
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.data.tables import MachineRow
from app.domain.enums import ReservationStatus
from app.services.ids import format_id
from tests.factories import make_reservation, make_slot, make_user

DAY = "2026-11-20"  # factories.START is 18:00 America/Toronto on this day


def _day_bounds(timezone: str = "America/Toronto"):
    tz = ZoneInfo(timezone)
    day = date.fromisoformat(DAY)
    start = datetime(day.year, day.month, day.day, tzinfo=tz)
    return start, start + timedelta(days=1)


def test_list_laundromats_ordered_by_name(client, db_session):
    from app.data.tables import LaundromatRow

    make_slot(db_session, label="Washer A")  # creates "Spin City"
    db_session.add(LaundromatRow(name="Alpha Wash", address="2 Side St"))
    db_session.commit()

    r = client.get("/laundromats")
    assert r.status_code == 200
    names = [lm["name"] for lm in r.json()["laundromats"]]
    assert names == sorted(names)
    assert "Alpha Wash" in names and "Spin City" in names
    assert all(lm["laundromatId"].startswith("lm_") for lm in r.json()["laundromats"])


def test_unknown_laundromat_is_404(client, db_engine):
    r = client.get("/laundromats/lm_999999999/slots", params={"date": DAY})
    assert r.status_code == 404
    assert r.json() == {"error": "not_found"}


def test_malformed_laundromat_id_is_404(client):
    r = client.get("/laundromats/not-an-id/slots", params={"date": DAY})
    assert r.status_code == 404
    assert r.json() == {"error": "not_found"}


def test_bad_date_is_422(client, db_session):
    slot = make_slot(db_session)
    db_session.commit()
    machine = db_session.get(MachineRow, slot.machine_id)
    r = client.get(f"/laundromats/lm_{machine.laundromat_id}/slots", params={"date": "20-11-2026"})
    assert r.status_code == 422
    assert r.json() == {"error": "invalid_request"}


@pytest.mark.parametrize(
    ("label", "status", "expires_delta", "expect_available"),
    [
        ("Open", None, None, True),
        ("LiveHold", ReservationStatus.HELD, timedelta(minutes=10), False),
        ("StaleHold", ReservationStatus.HELD, timedelta(minutes=-1), True),
        ("Booked", ReservationStatus.CONFIRMED, None, False),
        ("Cancelled", ReservationStatus.CANCELLED, None, True),
        ("Expired", ReservationStatus.EXPIRED, None, True),
        ("NoShow", ReservationStatus.NO_SHOW, None, True),
    ],
)
def test_read_model_agrees_with_is_available(db_session, uow_factory, label, status, expires_delta, expect_available):
    """THE pin: SQL `available` == MachineSlot.is_available(database now)."""
    user = make_user(db_session, email=f"{label.lower()}@example.com")
    slot = make_slot(db_session, label=label)
    if status is not None:
        expires = None if expires_delta is None else datetime.now(UTC) + expires_delta
        make_reservation(db_session, user, slot, status, expires_at=expires)
    db_session.commit()

    day_start, day_end = _day_bounds()
    machine = db_session.get(MachineRow, slot.machine_id)
    with uow_factory() as uow:
        found = uow.laundromats.reservable_slots_for_day(machine.laundromat_id, day_start, day_end)
        rows = {r.slot_id: r for r in found}
        loaded = uow.slots.get(slot.id)
        assert rows[slot.id].available is loaded.is_available(uow.slots.now())
        assert rows[slot.id].available is expect_available


def test_non_reservable_machines_are_hidden(client, db_session):
    from app.data.tables import LaundromatRow

    laundromat = LaundromatRow(name="Walk-in Only", address="9 Side St")
    db_session.add(laundromat)
    db_session.flush()
    make_slot(db_session, label="Washer Walk-in", laundromat=laundromat, reservable=False)
    make_slot(db_session, label="Washer Bookable", laundromat=laundromat, reservable=True)
    db_session.commit()

    r = client.get(f"/laundromats/lm_{laundromat.id}/slots", params={"date": DAY})
    assert r.status_code == 200
    labels = [m["label"] for m in r.json()["machines"]]
    assert labels == ["Washer Bookable"]


def test_slots_grid_marks_statuses(client, db_session):
    from app.data.tables import LaundromatRow

    user = make_user(db_session)
    laundromat = LaundromatRow(name="Grid Test", address="3 Test St")
    db_session.add(laundromat)
    db_session.flush()
    free = make_slot(db_session, label="Washer Free", laundromat=laundromat)
    taken = make_slot(db_session, label="Washer Taken", laundromat=laundromat)
    make_reservation(db_session, user, taken, ReservationStatus.CONFIRMED)
    db_session.commit()

    r = client.get(f"/laundromats/lm_{laundromat.id}/slots", params={"date": DAY})
    assert r.status_code == 200
    body = r.json()
    by_label = {m["label"]: m for m in body["machines"]}
    assert by_label["Washer Free"]["slots"][0]["status"] == "AVAILABLE"
    assert by_label["Washer Free"]["slots"][0]["slotId"] == format_id("slot", free.id)
    assert by_label["Washer Taken"]["slots"][0]["status"] == "UNAVAILABLE"
