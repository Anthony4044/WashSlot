"""Auth, judged over HTTP (US-8.4): a token is only as good as its signature.

A customer can read their own token: it is base64, not secret. These tests change it the way an
attacker would and expect 401 invalid_token every time, never 200 and never 403 (which would mean
the forged claims were believed). tests/test_security.py runs the same attacks inside the app.
"""
import base64
import json

from tests.conformance.contract import check, check_error
from tests.conformance.users import new_customer

MINE = "/me/reservations"
OPERATOR_ONLY = "/operator/laundromats"


def encode(data: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()


def decode(part: str) -> dict:
    return json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))


def token(customer) -> str:
    return customer["Authorization"].removeprefix("Bearer ")


def claims(customer) -> dict:
    return decode(token(customer).split(".")[1])


def with_claims(customer, **changes) -> dict[str, str]:
    """The customer's own token with some claims changed and the original signature kept."""
    header, _, signature = token(customer).split(".")
    forged = ".".join([header, encode({**claims(customer), **changes}), signature])
    return {"Authorization": f"Bearer {forged}"}


def test_the_untouched_token_works(api, customer):
    """The control: without it, the 401s below could have another cause."""
    r = api.get(MINE, headers={"Authorization": customer["Authorization"]})

    assert r.status_code == 200
    check(r, MINE, "get")


def test_a_customer_who_adds_operator_rights_to_their_token_gets_401(api, customer):
    headers = with_claims(customer, scope=f"{claims(customer)['scope']} operator:manage")

    check_error(api.get(OPERATOR_ONLY, headers=headers), OPERATOR_ONLY, "get", 401, "invalid_token")


def test_a_customer_who_puts_another_users_id_in_their_token_gets_401(api, customer):
    someone_else = claims(new_customer(api))["sub"]
    headers = with_claims(customer, sub=someone_else)

    check_error(api.get(MINE, headers=headers), MINE, "get", 401, "invalid_token")


def test_a_customer_who_makes_their_token_last_longer_gets_401(api, customer):
    headers = with_claims(customer, exp=claims(customer)["exp"] + 365 * 24 * 3600)

    check_error(api.get(MINE, headers=headers), MINE, "get", 401, "invalid_token")


def test_an_unsigned_token_that_says_alg_none_gets_401(api, customer):
    _, payload, _ = token(customer).split(".")
    unsigned = f"{encode({'alg': 'none', 'typ': 'JWT'})}.{payload}."

    check_error(api.get(MINE, headers={"Authorization": f"Bearer {unsigned}"}), MINE, "get", 401, "invalid_token")
