"""Errors the whole API shares. Example of a conformance test: call the server, then `check` it.

Copy this pattern for your endpoint: one test per documented response you can trigger.
"""
from tests.conformance.contract import ERROR_CODES, check_error


def test_unknown_route_is_404_not_found(api):
    r = api.get("/no-such-route")
    assert r.status_code == 404
    assert r.json() == {"error": "not_found"}
    assert "not_found" in ERROR_CODES


def test_unknown_laundromat_is_404_with_the_error_schema(api):
    r = api.get("/laundromats/lm_999999999/slots", params={"date": "2026-11-20"})
    check_error(r, "/laundromats/{laundromatId}/slots", "get", 404, "not_found")


def test_malformed_id_is_404_not_a_validation_error(api):
    r = api.get("/laundromats/not-an-id/slots", params={"date": "2026-11-20"})
    check_error(r, "/laundromats/{laundromatId}/slots", "get", 404, "not_found")
