"""Authentication and authorization over HTTP, including the three attacks (lecture Ch. 8).

"A token gives no security by itself. Checking it correctly does." A protected request must pass
EVERY check, on EVERY request (AccessTokens.verify in app/core/tokens.py). Skip any one and a forged
token gets in:

    check       what skipping it lets in                                 tested by
    ---------   ------------------------------------------------------   ------------------------------------
    signature   Attack A: tampered payload (edit claims, keep old sig)   test_attack_a_*
    algorithm   Attack B: alg=none, or HS256 keyed with our public key   test_attack_b_*
    issuer      a token made by some other identity provider             test_wrong_issuer_is_rejected
    audience    Attack C: a token made for another service               test_attack_c_*
                (the "confused deputy")
    expiry      an old token, after it ran out                           test_expired_token_is_rejected

The answers follow Chapter 3's error rules (app/api/security.py):
    401 missing_token        no Authorization header         "we don't know who you are"
    401 invalid_token        any check above fails           (never says which one: no hints for attackers)
    403 insufficient_scope   valid token, missing the scope  "we know you, but you may not do this"

There are no protected endpoints yet (they arrive with US-4.x), so the `protected` fixture builds an
app with three tiny test-only routes, guarded exactly the way real endpoints will be. No database needed.
"""
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


# --- helpers to build forged tokens by hand: header.payload.signature, each part base64url ----------

def b64url(data: bytes) -> str:
    """base64url without "=" padding, as JWTs use it."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def b64url_json(value: dict) -> str:
    return b64url(json.dumps(value, separators=(",", ":")).encode())


def unb64url_json(part: str) -> dict:
    return json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))


def valid_claims(tokens: AccessTokens, **changes) -> dict:
    """Claims that would pass every check, then `changes` applied (a change to None removes that claim)."""
    now = datetime.now(UTC)
    claims = {"sub": "usr_7", "scope": " ".join(CUSTOMER_SCOPES), "iss": tokens.issuer, "aud": tokens.audience,
              "iat": int(now.timestamp()), "exp": int((now + timedelta(minutes=60)).timestamp())}
    claims.update(changes)
    return {k: v for k, v in claims.items() if v is not None}


def sign(claims: dict, private_pem: bytes) -> str:
    """Sign arbitrary claims with OUR real private key, so the only thing wrong is the claims."""
    return jwt.encode(claims, load_private_key(private_pem), algorithm="RS256")


@pytest.fixture
def protected(access_tokens) -> TestClient:
    """An app with three test-only routes: one needs any valid token, two need a specific scope."""
    app = create_app()

    @app.get("/_test/me")  # authentication only: "who are you?"
    def me(user: Annotated[CurrentUser, Depends(get_current_user)]):
        return {"id": user.id, "scopes": sorted(user.scopes)}

    @app.get("/_test/write")  # + authorization: "may you write reservations?"
    def write(user: Annotated[CurrentUser, Depends(require_scope("reservations:write"))]):
        return {"id": user.id}

    @app.get("/_test/operator")  # + authorization: "may you manage a laundromat?"
    def operator(user: Annotated[CurrentUser, Depends(require_scope("operator:manage"))]):
        return {"id": user.id}

    app.dependency_overrides[get_access_tokens] = lambda: access_tokens  # throwaway test key pair
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
    assert r.json() == {"id": 7, "scopes": sorted(CUSTOMER_SCOPES)}  # the user id comes from the token's sub


def test_scope_present_lets_the_request_through(protected, bearer):
    r = protected.get("/_test/write", headers=bearer(7))
    assert r.status_code == 200
    assert r.json() == {"id": 7}


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
    """The expiry check: a genuine token issued 2 hours ago with a 60-minute lifetime."""
    token = access_tokens.issue("usr_7", CUSTOMER_SCOPES, now=datetime.now(UTC) - timedelta(hours=2))
    assert_invalid_token(call(protected, token))


# --- the three attacks (Ch. 8): each works only if the server skips ONE check ----------------

def test_attack_a_tampered_payload_is_rejected(protected, access_tokens):
    """Attack A, stopped by the SIGNATURE check.

    Take a real customer token, add "operator:manage" to its scope, and re-encode the payload. The
    old signature no longer matches the new payload, and the attacker can't make a new one without
    our private key.
    """
    header, payload, signature = access_tokens.issue("usr_7", CUSTOMER_SCOPES).split(".")
    claims = unb64url_json(payload)
    claims["scope"] += " operator:manage"
    forged = f"{header}.{b64url_json(claims)}.{signature}"
    assert_invalid_token(call(protected, forged, "/_test/operator"))


def test_attack_a_tampered_subject_is_rejected(protected, access_tokens):
    """Attack A again: keep the real signature but change sub to claim to be another user."""
    header, payload, signature = access_tokens.issue("usr_7", CUSTOMER_SCOPES).split(".")
    forged = f"{header}.{b64url_json({**unb64url_json(payload), 'sub': 'usr_1'})}.{signature}"
    assert_invalid_token(call(protected, forged))


@pytest.mark.parametrize("alg", ["none", "None", "NONE"])
def test_attack_b_alg_none_is_rejected(protected, access_tokens, alg):
    """Attack B, stopped by PINNING THE ALGORITHM (algorithms=["RS256"]).

    The header says "alg: none" (this token is not signed) and the signature part is empty. A
    server that lets the token's header choose how to check it would accept this with no key at all.
    """
    unsigned = f"{b64url_json({'alg': alg, 'typ': 'JWT'})}.{b64url_json(valid_claims(access_tokens))}."
    assert_invalid_token(call(protected, unsigned))


def test_attack_b_hs256_signed_with_our_public_key_is_rejected(protected, access_tokens, rsa_key_pair):
    """Attack B's related trick: algorithm confusion.

    The header says HS256 (a shared secret) and the "secret" used is our PUBLIC key, which everyone
    has. A server that used the public key as an HMAC secret would accept it. We only accept RS256.
    """
    signing_input = f"{b64url_json({'alg': 'HS256', 'typ': 'JWT'})}.{b64url_json(valid_claims(access_tokens))}"
    signature = hmac.new(rsa_key_pair[1], signing_input.encode(), hashlib.sha256).digest()
    assert_invalid_token(call(protected, f"{signing_input}.{b64url(signature)}"))


def test_attack_c_wrong_audience_is_rejected(protected, access_tokens, rsa_key_pair):
    """Attack C, the confused deputy, stopped by the AUDIENCE check.

    Every cryptographic check passes: it is signed with our real key, by our issuer, not expired.
    But its aud names another service. A token is only valid for the service it names.
    """
    private_pem, public_pem = rsa_key_pair
    other_service = AccessTokens(
        public_key=load_public_key(public_pem), private_key=load_private_key(private_pem),
        issuer=access_tokens.issuer, audience="https://some-other-api.example", expires_minutes=60,
    )
    assert_invalid_token(call(protected, other_service.issue("usr_7", CUSTOMER_SCOPES)))


def test_attack_c_missing_audience_is_rejected(protected, access_tokens, rsa_key_pair):
    """Attack C variant: no aud at all must not count as 'for everyone'."""
    token = sign(valid_claims(access_tokens, aud=None), rsa_key_pair[0])
    assert_invalid_token(call(protected, token))


# --- more forgeries -------------------------------------------------------------------------

def test_wrong_issuer_is_rejected(protected, access_tokens, rsa_key_pair):
    """The issuer check: the token must come from OUR login endpoint."""
    token = sign(valid_claims(access_tokens, iss="https://evil.example"), rsa_key_pair[0])
    assert_invalid_token(call(protected, token))


def test_token_signed_with_another_key_is_rejected(protected, access_tokens):
    """An attacker can make their own key pair and sign anything, but our public key rejects it."""
    attacker_private, _ = generate_key_pair(2048)
    token = sign(valid_claims(access_tokens), attacker_private)
    assert_invalid_token(call(protected, token))


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


# --- 403 insufficient_scope: authorization, after authentication succeeded --------------------

def test_missing_scope_is_403_insufficient_scope(protected, bearer):
    """A real, valid customer token on an operator route. We know who you are (not 401), but you may not (403)."""
    r = protected.get("/_test/operator", headers=bearer(7))
    assert r.status_code == 403
    assert r.json() == {"error": "insufficient_scope"}
    assert r.headers["WWW-Authenticate"] == 'Bearer error="insufficient_scope", scope="operator:manage"'


def test_read_only_token_cannot_write(protected, bearer):
    """Least privilege: a token with only reservations:read cannot write."""
    r = protected.get("/_test/write", headers=bearer(7, scopes=("reservations:read",)))
    assert r.status_code == 403
    assert r.json() == {"error": "insufficient_scope"}


def test_operator_token_reaches_operator_routes(protected, bearer):
    r = protected.get("/_test/operator", headers=bearer(3, scopes=("reservations:read", "operator:manage")))
    assert r.status_code == 200
    assert r.json() == {"id": 3}
