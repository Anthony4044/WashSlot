"""Interface-layer wiring that needs no database: error format and catalog, CORS, settings, DTOs."""
from fastapi.testclient import TestClient

from app.api.errors import CATALOG, ApiError
from app.api.responses import to_response
from app.api.schemas.base import RequestModel, ResponseModel
from app.core.config import BACKEND_DIR, Settings, to_sqlalchemy_url
from app.domain.errors import AlreadyCancelled, DomainError, HoldExpired, NotFound, SlotUnavailable
from app.main import create_app
from app.services.outcome import Outcome


def make_test_app() -> TestClient:
    app = create_app()

    @app.get("/_test/domain-conflict")
    def domain_conflict():
        raise SlotUnavailable()

    @app.get("/_test/api-error")
    def api_error():
        raise ApiError("idempotency_key_required")

    @app.get("/_test/unmapped")
    def unmapped():
        raise DomainError("code_nobody_mapped")

    @app.get("/_test/number/{n}")
    def number(n: int):
        return {"n": n}

    @app.get("/_test/crash")
    def crash():
        raise ValueError("boom")

    return TestClient(app, raise_server_exceptions=False)


def test_unknown_route_uses_error_format(api_client):
    r = api_client.get("/does-not-exist")
    assert r.status_code == 404
    assert r.json() == {"error": "not_found"}


def test_domain_error_is_mapped_by_the_interface_layer():
    r = make_test_app().get("/_test/domain-conflict")
    assert r.status_code == 409
    assert r.json() == {"error": "slot_unavailable"}


def test_api_error_uses_the_catalog():
    r = make_test_app().get("/_test/api-error")
    assert r.status_code == 422
    assert r.json() == {"error": "idempotency_key_required"}


def test_unmapped_code_fails_loudly_without_leaking():
    r = make_test_app().get("/_test/unmapped")
    assert r.status_code == 500
    assert r.json() == {"error": "internal_error"}


def test_every_domain_error_code_is_in_the_catalog():
    for error in (NotFound, SlotUnavailable, HoldExpired, AlreadyCancelled):
        assert error.code in CATALOG


def test_only_server_errors_are_retryable():
    for code, spec in CATALOG.items():
        assert spec.retryable == (spec.status >= 500), code


def test_validation_error_is_422_invalid_request():
    r = make_test_app().get("/_test/number/abc")
    assert r.status_code == 422
    assert r.json() == {"error": "invalid_request"}


def test_unexpected_error_is_500_without_details():
    r = make_test_app().get("/_test/crash")
    assert r.status_code == 500
    assert r.json() == {"error": "internal_error"}


def test_outcome_becomes_a_response():
    class HoldDto(ResponseModel):
        hold_id: str
        expires_at: str

    ok = to_response(Outcome.success(HoldDto(hold_id="hold_1", expires_at="2026-11-20T18:00:00Z")), 201)
    assert ok.status_code == 201
    assert ok.body == b'{"holdId":"hold_1","expiresAt":"2026-11-20T18:00:00Z"}'

    replayed = to_response(Outcome(ok=False, code="slot_unavailable", replayed=True))
    assert replayed.status_code == 409
    assert replayed.headers["Idempotency-Replayed"] == "true"


def test_request_models_are_camel_case_and_strict():
    class HoldRequest(RequestModel):
        confirmation_email: str

    assert HoldRequest.model_validate({"confirmationEmail": "a@b.c"}).confirmation_email == "a@b.c"
    try:
        HoldRequest.model_validate({"confirmationEmail": "a@b.c", "userId": 7})
        raise AssertionError("unknown fields must be rejected")
    except ValueError:
        pass


def test_cors_allows_the_react_dev_server(api_client):
    r = api_client.options(
        "/does-not-exist",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Authorization, Idempotency-Key",
        },
    )
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_cors_blocks_unknown_origins(api_client):
    r = api_client.options(
        "/does-not-exist",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
    )
    assert "access-control-allow-origin" not in r.headers


def test_neon_url_gets_psycopg_driver():
    url = "postgresql://u:p@ep-x.neon.tech/washslot?sslmode=require"
    assert to_sqlalchemy_url(url) == "postgresql+psycopg://u:p@ep-x.neon.tech/washslot?sslmode=require"
    assert to_sqlalchemy_url("postgresql+psycopg://h/db") == "postgresql+psycopg://h/db"


def test_settings_lists_and_key_paths():
    s = Settings(cors_origins="http://localhost:5173, https://washslot.example", jwt_public_key_file="keys/pub.pem")
    assert s.cors_origin_list == ["http://localhost:5173", "https://washslot.example"]
    assert s.jwt_public_key_file == BACKEND_DIR / "keys" / "pub.pem"
