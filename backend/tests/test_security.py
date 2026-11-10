"""The auth dependencies over HTTP, including the three attacks from CODING_GUIDE section 8:
tampered payload, alg=none, wrong audience. No database needed."""
import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
import pytest
from fastapi import Depends
from fastapi.testclient import TestClient

from app.api.deps import get_access_tokens
from app.api.security import CurrentUser, get_current_user, require_scope
from app.core.tokens import AccessTokens, load_private_key, load_public_key
from app.main import create_app
from scripts.generate_keys import generate_key_pair

CUSTOMER_SCOPES = ("reservations:read", "reservations:write")


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def b64url_json(value: dict) -> str:
    return b64url(json.dumps(value, separators=(",", ":")).encode())


def unb64url_json(part: str) -> dict:
    return json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))


def valid_claims(tokens: AccessTokens, **changes) -> dict:
    """Claims that would pass, minus/plus `changes` (a change to None removes that claim)."""
    now = datetime.now(UTC)
    claims = {"sub": "usr_7", "scope": " ".join(CUSTOMER_SCOPES), "iss": tokens.issuer, "aud": tokens.audience,
              "iat": int(now.timestamp()), "exp": int((now + timedelta(minutes=60)).timestamp())}
    claims.update(changes)
    return {k: v for k, v in claims.items() if v is not None}


def sign(claims: dict, private_pem: bytes) -> str:
    """Sign arbitrary claims with a real RSA key, so only the claims are wrong."""
    return jwt.encode(claims, load_private_key(private_pem), algorithm="RS256")


@pytest.fixture
def protected(access_tokens) -> TestClient:
    app = create_app()

    @app.get("/_test/me")
    def me(user: Annotated[CurrentUser, Depends(get_current_user)]):
        return {"id": user.id, "scopes": sorted(user.scopes)}

    @app.get("/_test/write")
    def write(user: Annotated[CurrentUser, Depends(require_scope("reservations:write"))]):
        return {"id": user.id}

    @app.get("/_test/operator")
    def operator(user: Annotated[CurrentUser, Depends(require_scope("operator:manage"))]):
        return {"id": user.id}

    app.dependency_overrides[get_access_tokens] = lambda: access_tokens
    return TestClient(app)


def call(client: TestClient, token: str | None, path: str = "/_test/me", scheme: str = "Bearer"):
    headers = {} if token is None else {"Authorization": f"{scheme} {token}"}
    return client.get(path, headers=headers)


def assert_invalid_token(response):
    assert response.status_code == 401
    assert response.json() == {"error": "invalid_token"}
    assert response.headers["WWW-Authenticate"] == 'Bearer error="invalid_token"'


# --- the happy path -------------------------------------------------------------------------

def test_valid_token_identifies_the_user(protected, bearer):
    r = protected.get("/_test/me", headers=bearer(7))
    assert r.status_code == 200
    assert r.json() == {"id": 7, "scopes": sorted(CUSTOMER_SCOPES)}


def test_scope_present_lets_the_request_through(protected, bearer):
    r = protected.get("/_test/write", headers=bearer(7))
    assert r.status_code == 200 and r.json() == {"id": 7}


# --- 401 missing_token / invalid_token ------------------------------------------------------

def test_no_token_is_401_missing_token(protected):
    r = call(protected, None)
    assert r.status_code == 401
    assert r.json() == {"error": "missing_token"}
    assert r.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.parametrize("header", ["Basic dXNlcjpwYXNz", "Bearer", "Bearer ", "token-without-scheme"])
def test_malformed_authorization_header_is_invalid_token(protected, header):
    assert_invalid_token(protected.get("/_test/me", headers={"Authorization": header}))


@pytest.mark.parametrize("garbage", ["abc", "a.b.c", "....", "eyJhbGciOiJSUzI1NiJ9.e30.x"])
def test_garbage_token_is_invalid_token(protected, garbage):
    assert_invalid_token(call(protected, garbage))


def test_expired_token_is_rejected(protected, access_tokens):
    token = access_tokens.issue("usr_7", CUSTOMER_SCOPES, now=datetime.now(UTC) - timedelta(hours=2))
    assert_invalid_token(call(protected, token))


# --- the three attacks ----------------------------------------------------------------------

def test_attack_tampered_payload_is_rejected(protected, access_tokens):
    """Keep the real signature but give yourself operator rights in the payload."""
    header, payload, signature = access_tokens.issue("usr_7", CUSTOMER_SCOPES).split(".")
    claims = unb64url_json(payload)
    claims["scope"] += " operator:manage"
    forged = f"{header}.{b64url_json(claims)}.{signature}"
    assert_invalid_token(call(protected, forged, "/_test/operator"))


def test_attack_tampered_subject_is_rejected(protected, access_tokens):
    """Keep the real signature but claim to be another user."""
    header, payload, signature = access_tokens.issue("usr_7", CUSTOMER_SCOPES).split(".")
    forged = f"{header}.{b64url_json({**unb64url_json(payload), 'sub': 'usr_1'})}.{signature}"
    assert_invalid_token(call(protected, forged))


@pytest.mark.parametrize("alg", ["none", "None", "NONE"])
def test_attack_alg_none_is_rejected(protected, access_tokens, alg):
    """An unsigned token that says it needs no signature."""
    unsigned = f"{b64url_json({'alg': alg, 'typ': 'JWT'})}.{b64url_json(valid_claims(access_tokens))}."
    assert_invalid_token(call(protected, unsigned))


def test_attack_wrong_audience_is_rejected(protected, access_tokens, rsa_key_pair):
    """A genuine token, signed with our key, but issued for another service."""
    private_pem, public_pem = rsa_key_pair
    other_service = AccessTokens(
        public_key=load_public_key(public_pem), private_key=load_private_key(private_pem),
        issuer=access_tokens.issuer, audience="https://some-other-api.example", expires_minutes=60,
    )
    assert_invalid_token(call(protected, other_service.issue("usr_7", CUSTOMER_SCOPES)))


def test_missing_audience_is_rejected(protected, access_tokens, rsa_key_pair):
    token = sign(valid_claims(access_tokens, aud=None), rsa_key_pair[0])
    assert_invalid_token(call(protected, token))


# --- more forgeries -------------------------------------------------------------------------

def test_wrong_issuer_is_rejected(protected, access_tokens, rsa_key_pair):
    token = sign(valid_claims(access_tokens, iss="https://evil.example"), rsa_key_pair[0])
    assert_invalid_token(call(protected, token))


def test_token_signed_with_another_key_is_rejected(protected, access_tokens):
    attacker_private, _ = generate_key_pair(2048)
    token = sign(valid_claims(access_tokens), attacker_private)
    assert_invalid_token(call(protected, token))


def test_hs256_signed_with_our_public_key_is_rejected(protected, access_tokens, rsa_key_pair):
    """Algorithm confusion: the public key is public, so an attacker can use it as an HMAC secret."""
    signing_input = f"{b64url_json({'alg': 'HS256', 'typ': 'JWT'})}.{b64url_json(valid_claims(access_tokens))}"
    signature = hmac.new(rsa_key_pair[1], signing_input.encode(), hashlib.sha256).digest()
    assert_invalid_token(call(protected, f"{signing_input}.{b64url(signature)}"))


@pytest.mark.parametrize("missing", ["sub", "scope", "exp", "iat"])
def test_token_missing_a_required_claim_is_rejected(protected, access_tokens, rsa_key_pair, missing):
    token = sign(valid_claims(access_tokens, **{missing: None}), rsa_key_pair[0])
    assert_invalid_token(call(protected, token))


@pytest.mark.parametrize("subject", ["7", "usr_0", "lm_7", "usr_7x", ""])
def test_subject_that_is_not_a_user_id_is_rejected(protected, access_tokens, subject):
    assert_invalid_token(call(protected, access_tokens.issue(subject, CUSTOMER_SCOPES)))


def test_non_string_scope_is_rejected(protected, access_tokens, rsa_key_pair):
    token = sign(valid_claims(access_tokens, scope=["operator:manage"]), rsa_key_pair[0])
    assert_invalid_token(call(protected, token))


# --- 403 insufficient_scope -----------------------------------------------------------------

def test_missing_scope_is_403_insufficient_scope(protected, bearer):
    r = protected.get("/_test/operator", headers=bearer(7))
    assert r.status_code == 403
    assert r.json() == {"error": "insufficient_scope"}
    assert r.headers["WWW-Authenticate"] == 'Bearer error="insufficient_scope", scope="operator:manage"'


def test_read_only_token_cannot_write(protected, bearer):
    r = protected.get("/_test/write", headers=bearer(7, scopes=("reservations:read",)))
    assert r.status_code == 403 and r.json() == {"error": "insufficient_scope"}


def test_operator_token_reaches_operator_routes(protected, bearer):
    r = protected.get("/_test/operator", headers=bearer(3, scopes=("reservations:read", "operator:manage")))
    assert r.status_code == 200 and r.json() == {"id": 3}
