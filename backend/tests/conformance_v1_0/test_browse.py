"""GET /laundromats and GET /laundromats/{id}/slots, judged by the contract alone."""
from datetime import date, timedelta

from tests.conformance_v1_0.contract import check, check_error

LIST = "/laundromats"
SLOTS = "/laundromats/{laundromatId}/slots"


def test_list_laundromats(api):
    r = api.get(LIST)
    body = check(r, LIST, "get")
    assert r.status_code == 200
    assert "laundromats" in body
    for lm in body["laundromats"]:
        assert lm["laundromatId"].startswith("lm_")
        assert lm["name"] and lm["address"] and lm["timezone"]


def test_slots_for_a_seeded_laundromat(api):
    listing = check(api.get(LIST), LIST, "get")
    if not listing["laundromats"]:
        import pytest

        pytest.skip("no laundromats: run scripts/seed_laundromats.py")

    laundromat_id = listing["laundromats"][0]["laundromatId"]
    day = (date.today() + timedelta(days=1)).isoformat()
    r = api.get(f"/laundromats/{laundromat_id}/slots", params={"date": day})
    body = check(r, SLOTS, "get")
    assert r.status_code == 200
    for machine in body["machines"]:
        assert machine["machineId"].startswith("mch_")
        assert machine["type"] in ("WASHER", "DRYER")
        for slot in machine["slots"]:
            assert slot["slotId"].startswith("slot_")
            assert slot["status"] in ("AVAILABLE", "UNAVAILABLE")


def test_unknown_laundromat_is_404(api):
    check_error(
        api.get("/laundromats/lm_999999999/slots", params={"date": "2026-11-20"}),
        SLOTS,
        "get",
        404,
        "not_found",
    )


def test_malformed_laundromat_id_is_404(api):
    check_error(
        api.get("/laundromats/not-an-id/slots", params={"date": "2026-11-20"}),
        SLOTS,
        "get",
        404,
        "not_found",
    )


def test_missing_date_is_422(api):
    listing = api.get(LIST)
    if listing.status_code != 200 or not listing.json().get("laundromats"):
        import pytest

        pytest.skip("no laundromats: run scripts/seed_laundromats.py")
    laundromat_id = listing.json()["laundromats"][0]["laundromatId"]
    check_error(api.get(f"/laundromats/{laundromat_id}/slots"), SLOTS, "get", 422, "invalid_request")
