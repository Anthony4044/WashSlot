"""POST /auth/register and POST /auth/login, judged by the contract alone (lecture Ch. 2).

These tests talk HTTP to a running server and never import `app`, so they would judge a Java
version of WashSlot exactly the same way. Two helpers do the judging (tests/conformance/contract.py):
- check(response, path, method):  the status must be one the contract documents for this operation,
  and the body must match the contract's JSON Schema for that status. Returns the parsed body.
- check_error(..., status, code):  the same, plus this exact status and {"error": code}.

Run them (from backend/):
    uvicorn app.main:app                                                    # terminal 1
    CONFORMANCE_BASE_URL=http://localhost:8000 pytest tests/conformance     # terminal 2
"""
import base64
import json

import pytest

from tests.conformance_v1_0.contract import check, check_error
from tests.conformance_v1_0.users import PASSWORD, unique_email

REGISTER, LOGIN = "/auth/register", "/auth/login"


def jwt_part(token: str, index: int) -> dict:
    """Decode part 0 (the header) or part 1 (the payload) of a JWT.

    No key needed: a JWT is signed, not encrypted (Ch. 8). Anyone can READ it; only the server's
    private key can MAKE one that passes the signature check.
    """
    part = token.split(".")[index]
    return json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))  # base64url has no "=" padding


# --- POST /auth/register ------------------------------------------------------------------------

def test_register_creates_a_customer(api):
    email = unique_email()
    r = api.post(REGISTER, json={"email": email, "password": PASSWORD})
    assert r.status_code == 201
    body = check(r, REGISTER, "post")
    assert body["email"] == email
    assert body["role"] == "CUSTOMER"


def test_register_twice_is_409_email_taken(api):
    email = unique_email()
    api.post(REGISTER, json={"email": email, "password": PASSWORD})
    r = api.post(REGISTER, json={"email": email.upper(), "password": PASSWORD})  # same email, other letter case
    check_error(r, REGISTER, "post", 409, "email_taken")


def test_register_with_a_role_field_is_422_and_creates_nothing(api):
    """Asking for OPERATOR is refused, and no account of any kind is created.

    The contract's RegisterRequest has no "role" property and additionalProperties: false.
    """
    email = unique_email()
    r = api.post(REGISTER, json={"email": email, "password": PASSWORD, "role": "OPERATOR"})
    check_error(r, REGISTER, "post", 422, "invalid_request")

    # Proof that nothing was created: these credentials don't log in...
    r = api.post(LOGIN, json={"email": email, "password": PASSWORD})
    check_error(r, LOGIN, "post", 401, "invalid_credentials")
    # ...and the email is still free. The account you CAN create with it is a customer.
    r = api.post(REGISTER, json={"email": email, "password": PASSWORD})
    assert r.status_code == 201
    assert check(r, REGISTER, "post")["role"] == "CUSTOMER"


@pytest.mark.parametrize("body", [
    {"email": unique_email(), "password": "short"},  # contract: password minLength 8
    {"email": unique_email(), "password": "x" * 73},  # contract: password maxLength 72 (bcrypt's limit)
    {"email": "not-an-email", "password": PASSWORD},  # contract: email has format: email
    {"email": unique_email()},  # contract: password is required
    {"password": PASSWORD},  # contract: email is required
])
def test_register_with_a_bad_body_is_422_invalid_request(api, body):
    check_error(api.post(REGISTER, json=body), REGISTER, "post", 422, "invalid_request")


# --- POST /auth/login ---------------------------------------------------------------------------

def test_login_returns_a_token_with_customer_scopes(api, customer):
    r = api.post(LOGIN, json={"email": customer["email"], "password": PASSWORD})
    assert r.status_code == 200
    body = check(r, LOGIN, "post")  # the schema also pins tokenType "Bearer" and expiresIn >= 1
    assert set(body["scope"].split()) == {"reservations:read", "reservations:write"}  # no operator:manage


def test_login_token_is_an_rs256_jwt_carrying_its_scopes(api, customer):
    """The contract says login 'returns a JWT signed with RS256', and its security scheme says the
    server checks iss, aud and exp and reads the space-separated "scope" claim. Look inside the token."""
    body = check(api.post(LOGIN, json={"email": customer["email"], "password": PASSWORD}), LOGIN, "post")
    token = body["accessToken"]

    assert token.count(".") == 2  # header.payload.signature
    assert jwt_part(token, 0)["alg"] == "RS256"  # a key pair, never a shared secret or "none"
    payload = jwt_part(token, 1)
    assert {"sub", "scope", "iss", "aud", "exp"} <= payload.keys()  # the claims a verifier checks
    assert payload["scope"] == body["scope"]  # the body reports exactly what the token grants


def test_wrong_password_is_401_invalid_credentials(api, customer):
    r = api.post(LOGIN, json={"email": customer["email"], "password": "wrong-password"})
    check_error(r, LOGIN, "post", 401, "invalid_credentials")


def test_unknown_email_is_the_same_401_as_a_wrong_password(api):
    """The response never says WHICH one was wrong, so login can't be used to find out who has an account."""
    r = api.post(LOGIN, json={"email": unique_email(), "password": PASSWORD})
    check_error(r, LOGIN, "post", 401, "invalid_credentials")


@pytest.mark.parametrize("body", [
    {"email": "someone@example.com"},  # contract: password is required
    {"password": PASSWORD},  # contract: email is required
    {"email": "", "password": PASSWORD},  # contract: email minLength 1
    {"email": "someone@example.com", "password": PASSWORD, "scope": "operator:manage"},  # strict body
])
def test_login_with_a_bad_body_is_422_invalid_request(api, body):
    check_error(api.post(LOGIN, json=body), LOGIN, "post", 422, "invalid_request")
