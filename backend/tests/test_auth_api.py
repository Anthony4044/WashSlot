"""POST /auth/register and POST /auth/login against the test database, plus the seed script.
Skipped without TEST_DATABASE_URL."""
import re
import threading

import bcrypt
import pytest
from sqlalchemy import func, select

from app.data.tables import UserRow
from app.domain.enums import UserRole
from app.services.auth import AuthService
from scripts.seed_users import SEED_USERS, seed

USER_ID = re.compile(r"^usr_[1-9][0-9]*$")


def register(client, email="alice@example.com", password="correct horse", **extra):
    return client.post("/auth/register", json={"email": email, "password": password, **extra})


def login(client, email="alice@example.com", password="correct horse"):
    return client.post("/auth/login", json={"email": email, "password": password})


def user_count(db_session) -> int:
    return db_session.scalar(select(func.count()).select_from(UserRow))


# --- register -------------------------------------------------------------------------------

def test_register_is_201_with_the_new_customer(client, db_session):
    r = register(client, email="Alice@Example.com")
    assert r.status_code == 201
    body = r.json()
    assert set(body) == {"userId", "email", "role"}
    assert USER_ID.match(body["userId"])
    assert body["email"] == "alice@example.com" and body["role"] == "CUSTOMER"

    row = db_session.scalars(select(UserRow)).one()
    assert row.email == "alice@example.com" and row.role == UserRole.CUSTOMER
    assert bcrypt.checkpw(b"correct horse", row.password_hash.encode())


@pytest.mark.parametrize("smuggled", [{"role": "OPERATOR"}, {"role": "CUSTOMER"}, {"scope": "operator:manage"}])
def test_register_cannot_choose_a_role(client, db_session, smuggled):
    """The body is strict, so a role field is refused outright and no account is created at all."""
    r = register(client, **smuggled)
    assert r.status_code == 422 and r.json() == {"error": "invalid_request"}
    assert user_count(db_session) == 0


def test_register_twice_is_409_email_taken(client, db_session):
    assert register(client).status_code == 201
    r = register(client, email="ALICE@example.com", password="different pw")
    assert r.status_code == 409 and r.json() == {"error": "email_taken"}
    assert user_count(db_session) == 1


@pytest.mark.parametrize("body", [
    {"email": "alice@example.com", "password": "short"},  # under 8 characters
    {"email": "alice@example.com", "password": "é" * 37},  # over bcrypt's 72 bytes
    {"email": "not-an-email", "password": "correct horse"},
    {"email": "alice@example.com"},
    {"password": "correct horse"},
])
def test_register_rejects_bad_input_with_422(client, db_session, body):
    r = client.post("/auth/register", json=body)
    assert r.status_code == 422 and r.json() == {"error": "invalid_request"}
    assert user_count(db_session) == 0


def test_racing_sign_ups_for_one_email_create_one_account(uow_factory, password_hasher, access_tokens, db_session):
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
    r = login(client, email=" ALICE@example.com ")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"accessToken", "tokenType", "expiresIn", "scope"}
    assert body["tokenType"] == "Bearer" and body["expiresIn"] == 3600
    assert body["scope"] == "reservations:read reservations:write"
    assert access_tokens.verify(body["accessToken"]).subject == user_id


def test_login_wrong_password_is_401_invalid_credentials(client):
    register(client)
    r = login(client, password="wrong horse")
    assert r.status_code == 401 and r.json() == {"error": "invalid_credentials"}


def test_login_unknown_email_is_the_same_401(client):
    r = login(client, email="nobody@example.com")
    assert r.status_code == 401 and r.json() == {"error": "invalid_credentials"}


def test_login_body_is_strict(client):
    r = client.post("/auth/login", json={"email": "a@example.com", "password": "x", "scope": "operator:manage"})
    assert r.status_code == 422 and r.json() == {"error": "invalid_request"}


# --- scripts/seed_users.py ------------------------------------------------------------------

def test_seed_creates_two_customers_and_one_operator_once(uow_factory, password_hasher, db_session):
    assert [created for _, created in seed(uow_factory, password_hasher)] == [True, True, True]
    assert [created for _, created in seed(uow_factory, password_hasher)] == [False, False, False]
    roles = db_session.execute(select(UserRow.role).order_by(UserRow.id)).scalars().all()
    assert roles == [UserRole.CUSTOMER, UserRole.CUSTOMER, UserRole.OPERATOR]


def test_seeded_operator_logs_in_with_operator_manage(client, uow_factory, password_hasher):
    seed(uow_factory, password_hasher)
    email, password, _ = next(u for u in SEED_USERS if u[2] == UserRole.OPERATOR)
    r = login(client, email, password)
    assert r.status_code == 200
    assert r.json()["scope"] == "reservations:read reservations:write operator:manage"
