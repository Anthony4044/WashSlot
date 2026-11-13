"""POST /auth/register and POST /auth/login over HTTP, against the test database, plus the seed script.

These go through every layer (route -> service -> domain -> repository -> Postgres), so they need
TEST_DATABASE_URL and are skipped without it. The `client` fixture (tests/conftest.py) wires the app to
the test database, a throwaway RSA key pair, and fast bcrypt.
"""
import re
import threading
from typing import Annotated

import bcrypt
import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.api.deps import get_access_tokens, get_password_hasher, get_uow_factory
from app.api.security import CurrentUser, require_scope
from app.data.tables import UserRow
from app.domain.enums import UserRole
from app.main import create_app
from app.services.auth import AuthService
from app.services.ids import USER, format_id
from scripts.seed_users import SEED_USERS, seed

USER_ID = re.compile(r"^usr_[1-9][0-9]*$")  # the contract's UserId pattern


def register(client, email="alice@example.com", password="correct horse", **extra):
    return client.post("/auth/register", json={"email": email, "password": password, **extra})


def login(client, email="alice@example.com", password="correct horse"):
    return client.post("/auth/login", json={"email": email, "password": password})


def bearer_header(login_response) -> dict[str, str]:
    """What a client does with the login response: send the token back on every request."""
    return {"Authorization": f"Bearer {login_response.json()['accessToken']}"}


def user_count(db_session) -> int:
    return db_session.scalar(select(func.count()).select_from(UserRow))


@pytest.fixture
def protected_client(uow_factory, access_tokens, password_hasher):
    """The real app (register, login, test database) plus two test-only protected routes.

    No real endpoint needs a token yet (that starts with US-4.x), so these stand in for one.
    """
    app = create_app()

    @app.get("/_test/me")  # needs reservations:write, like placing a hold will
    def me(user: Annotated[CurrentUser, Depends(require_scope("reservations:write"))]):
        return {"userId": format_id(USER, user.id), "scopes": sorted(user.scopes)}

    @app.get("/_test/operator")  # needs operator:manage, like the operator tools will
    def operator(user: Annotated[CurrentUser, Depends(require_scope("operator:manage"))]):
        return {"userId": format_id(USER, user.id)}

    app.dependency_overrides.update({
        get_uow_factory: lambda: uow_factory,
        get_access_tokens: lambda: access_tokens,
        get_password_hasher: lambda: password_hasher,
    })
    with TestClient(app) as client:
        yield client


# --- register -------------------------------------------------------------------------------

def test_register_is_201_with_the_new_customer(client, db_session):
    r = register(client, email="Alice@Example.com")
    assert r.status_code == 201
    body = r.json()
    assert set(body) == {"userId", "email", "role"}
    assert USER_ID.match(body["userId"])
    assert body["email"] == "alice@example.com"  # stored lower-case (normalize_email)
    assert body["role"] == "CUSTOMER"

    # And in the database: a customer row with a bcrypt hash, never the password itself.
    row = db_session.scalars(select(UserRow)).one()
    assert row.email == "alice@example.com"
    assert row.role == UserRole.CUSTOMER
    assert bcrypt.checkpw(b"correct horse", row.password_hash.encode())


@pytest.mark.parametrize("smuggled", [{"role": "OPERATOR"}, {"role": "CUSTOMER"}, {"scope": "operator:manage"}])
def test_register_cannot_choose_a_role(client, db_session, smuggled):
    """The body is strict, so a role field is refused outright and no account is created at all."""
    r = register(client, **smuggled)
    assert r.status_code == 422
    assert r.json() == {"error": "invalid_request"}
    assert user_count(db_session) == 0


def test_register_twice_is_409_email_taken(client, db_session):
    assert register(client).status_code == 201
    r = register(client, email="ALICE@example.com", password="different pw")  # same email, other case
    assert r.status_code == 409
    assert r.json() == {"error": "email_taken"}
    assert user_count(db_session) == 1


@pytest.mark.parametrize("body", [
    {"email": "alice@example.com", "password": "short"},  # under 8 characters
    {"email": "alice@example.com", "password": "é" * 37},  # only 37 characters, but 74 bytes: over bcrypt's 72
    {"email": "not-an-email", "password": "correct horse"},
    {"email": "alice@example.com"},
    {"password": "correct horse"},
])
def test_register_rejects_bad_input_with_422(client, db_session, body):
    r = client.post("/auth/register", json=body)
    assert r.status_code == 422
    assert r.json() == {"error": "invalid_request"}
    assert user_count(db_session) == 0


def test_racing_sign_ups_for_one_email_create_one_account(uow_factory, password_hasher, access_tokens, db_session):
    """8 threads register the same email at the same moment (the barrier releases them together).

    Exactly one wins. The database's unique constraint decides (SqlUserRepository.add), so there is
    no check-then-act race (Ch. 7).
    """
    service = AuthService(uow_factory, password_hasher, access_tokens)
    n = 8
    barrier, outcomes = threading.Barrier(n), []

    def sign_up():
        barrier.wait()
        outcomes.append(service.register("alice@example.com", "correct horse"))

    threads = [threading.Thread(target=sign_up) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sum(o.ok for o in outcomes) == 1
    assert sorted(o.code for o in outcomes if not o.ok) == ["email_taken"] * (n - 1)
    assert user_count(db_session) == 1


# --- login ----------------------------------------------------------------------------------

def test_login_returns_a_bearer_token_for_that_user(client, access_tokens):
    user_id = register(client).json()["userId"]
    r = login(client, email=" ALICE@example.com ")  # spaces and case don't matter
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"accessToken", "tokenType", "expiresIn", "scope"}
    assert body["tokenType"] == "Bearer"
    assert body["expiresIn"] == 3600  # the test key pair's 60 minutes
    assert body["scope"] == "reservations:read reservations:write"
    assert access_tokens.verify(body["accessToken"]).subject == user_id  # the token's sub is this user


def test_login_wrong_password_is_401_invalid_credentials(client):
    register(client)
    r = login(client, password="wrong horse")
    assert r.status_code == 401
    assert r.json() == {"error": "invalid_credentials"}


def test_login_unknown_email_is_the_same_401(client):
    r = login(client, email="nobody@example.com")
    assert r.status_code == 401
    assert r.json() == {"error": "invalid_credentials"}


def test_login_body_is_strict(client):
    r = client.post("/auth/login", json={"email": "a@example.com", "password": "x", "scope": "operator:manage"})
    assert r.status_code == 422
    assert r.json() == {"error": "invalid_request"}


# --- the whole story: login -> token -> protected request (Ch. 8, "the JWT lifecycle") --------

def test_the_login_token_opens_a_protected_endpoint(protected_client):
    """Log in, the server issues a token, the client sends it as "Authorization: Bearer ...",
    the server verifies it with the public key and knows who is calling, with no session lookup."""
    user_id = register(protected_client).json()["userId"]
    r = protected_client.get("/_test/me", headers=bearer_header(login(protected_client)))
    assert r.status_code == 200
    assert r.json() == {"userId": user_id, "scopes": ["reservations:read", "reservations:write"]}


def test_registering_as_operator_never_gives_operator_rights(protected_client):
    """T.2.1.6 "register with role: OPERATOR": the request is refused, and the account you CAN
    create is a customer whose token gets 403 on operator routes (least privilege)."""
    assert register(protected_client, role="OPERATOR").status_code == 422

    assert register(protected_client).json()["role"] == "CUSTOMER"
    r = protected_client.get("/_test/operator", headers=bearer_header(login(protected_client)))
    assert r.status_code == 403  # a valid token (not 401), just not allowed here
    assert r.json() == {"error": "insufficient_scope"}


def test_seeded_operator_token_opens_operator_routes(protected_client, uow_factory, password_hasher):
    """The only way to get an operator is the seed script, and its token does carry operator:manage."""
    seed(uow_factory, password_hasher)
    email, password, _ = next(u for u in SEED_USERS if u[2] == UserRole.OPERATOR)
    r = protected_client.get("/_test/operator", headers=bearer_header(login(protected_client, email, password)))
    assert r.status_code == 200


# --- scripts/seed_users.py ------------------------------------------------------------------

def test_seed_creates_two_customers_and_one_operator_once(uow_factory, password_hasher, db_session):
    assert [created for _, created in seed(uow_factory, password_hasher)] == [True, True, True]
    assert [created for _, created in seed(uow_factory, password_hasher)] == [False, False, False]  # rerun: no-op
    roles = db_session.execute(select(UserRow.role).order_by(UserRow.id)).scalars().all()
    assert roles == [UserRole.CUSTOMER, UserRole.CUSTOMER, UserRole.OPERATOR]


def test_seeded_operator_logs_in_with_operator_manage(client, uow_factory, password_hasher):
    seed(uow_factory, password_hasher)
    email, password, _ = next(u for u in SEED_USERS if u[2] == UserRole.OPERATOR)
    r = login(client, email, password)
    assert r.status_code == 200
    assert r.json()["scope"] == "reservations:read reservations:write operator:manage"
