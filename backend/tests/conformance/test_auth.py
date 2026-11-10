"""POST /auth/register and POST /auth/login, judged by the contract."""
from tests.conformance.contract import check, check_error
from tests.conformance.users import PASSWORD, unique_email

REGISTER, LOGIN = "/auth/register", "/auth/login"


def test_register_creates_a_customer(api):
    email = unique_email()
    r = api.post(REGISTER, json={"email": email, "password": PASSWORD})
    assert r.status_code == 201
    body = check(r, REGISTER, "post")
    assert body["email"] == email and body["role"] == "CUSTOMER"


def test_register_twice_is_409_email_taken(api):
    email = unique_email()
    api.post(REGISTER, json={"email": email, "password": PASSWORD})
    r = api.post(REGISTER, json={"email": email.upper(), "password": PASSWORD})
    check_error(r, REGISTER, "post", 409, "email_taken")


def test_register_rejects_a_role_field(api):
    r = api.post(REGISTER, json={"email": unique_email(), "password": PASSWORD, "role": "OPERATOR"})
    check_error(r, REGISTER, "post", 422, "invalid_request")


def test_login_returns_a_token_with_customer_scopes(api, customer):
    r = api.post(LOGIN, json={"email": customer["email"], "password": PASSWORD})
    assert r.status_code == 200
    body = check(r, LOGIN, "post")
    assert set(body["scope"].split()) == {"reservations:read", "reservations:write"}


def test_wrong_password_is_401_invalid_credentials(api, customer):
    r = api.post(LOGIN, json={"email": customer["email"], "password": "wrong-password"})
    check_error(r, LOGIN, "post", 401, "invalid_credentials")
