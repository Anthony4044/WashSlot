"""Shared test fixtures. Three levels of test:

- domain tests:        plain objects, no fixtures, no database (tests/test_domain_*.py)
- service tests:       use cases against app.data.memory doubles (`memory_uow`)
- database / API tests: against TEST_DATABASE_URL (`db_engine`, `uow_factory`, `client`)
- conformance tests:   the running API checked against contract/openapi.yaml (tests/conformance/)

Auth: `client` and `api_client` sign tokens with a throwaway key pair (no key files needed) and
hash passwords with cheap bcrypt. To call a protected endpoint: `client.get(url, headers=bearer(user_id))`.

Database tests are skipped if TEST_DATABASE_URL is not set.
- Once per test run: every table is dropped and rebuilt with the real Alembic migrations.
- Before each test: every table is emptied (TRUNCATE), so each test starts clean.
We empty tables instead of rolling back because concurrency tests need several connections that
really commit, exactly like production.
"""
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from app.api.deps import get_access_tokens, get_password_hasher, get_uow_factory
from app.core.config import get_settings, to_sqlalchemy_url
from app.core.passwords import PasswordHasher
from app.core.tokens import AccessTokens, load_private_key, load_public_key
from app.data.database import make_engine, make_session_factory
from app.data.memory import MemoryUnitOfWork
from app.data.tables import Base
from app.data.unit_of_work import SqlAlchemyUnitOfWork
from app.domain.enums import UserRole
from app.domain.user import SCOPES_BY_ROLE
from app.main import app
from app.services.ids import USER, format_id
from app.services.unit_of_work import UnitOfWorkFactory
from scripts.generate_keys import generate_key_pair

BACKEND_DIR = Path(__file__).resolve().parents[1]
TEST_ISSUER = "https://auth.washslot.test"
TEST_AUDIENCE = "https://api.washslot.test"


@pytest.fixture(scope="session")
def test_engine() -> Iterator[Engine]:
    settings = get_settings()
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not set")
    if settings.database_url and to_sqlalchemy_url(settings.test_database_url) == to_sqlalchemy_url(
        settings.database_url
    ):
        pytest.exit("TEST_DATABASE_URL must not be the same database as DATABASE_URL", returncode=1)

    engine = make_engine(settings.test_database_url)
    with engine.begin() as conn:
        # Wipe everything, including tables from another branch's migrations (e.g. after switching
        # branches), so the run always starts from an empty database.
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
        cfg = Config(str(BACKEND_DIR / "alembic.ini"))
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")
    yield engine
    engine.dispose()


@pytest.fixture
def db_engine(test_engine: Engine) -> Engine:
    """The test database, emptied before this test."""
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    with test_engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    return test_engine


@pytest.fixture
def db_session(db_engine: Engine) -> Iterator[Session]:
    """A session for arranging data and checking results directly in the database."""
    with Session(db_engine, expire_on_commit=False) as session:
        yield session


@pytest.fixture
def uow_factory(db_engine: Engine) -> UnitOfWorkFactory:
    """Real units of work on the test database, as the services get them in production."""
    session_factory = make_session_factory(db_engine)
    return lambda: SqlAlchemyUnitOfWork(session_factory)


@pytest.fixture
def memory_uow() -> MemoryUnitOfWork:
    """In-memory unit of work for fast service-layer tests. Pass it where a factory is expected."""
    return MemoryUnitOfWork()


@pytest.fixture(scope="session")
def rsa_key_pair() -> tuple[bytes, bytes]:
    """(private PEM, public PEM), made once per test run."""
    return generate_key_pair(2048)


@pytest.fixture(scope="session")
def access_tokens(rsa_key_pair) -> AccessTokens:
    private_pem, public_pem = rsa_key_pair
    return AccessTokens(public_key=load_public_key(public_pem), private_key=load_private_key(private_pem),
                        issuer=TEST_ISSUER, audience=TEST_AUDIENCE, expires_minutes=60)


@pytest.fixture(scope="session")
def password_hasher() -> PasswordHasher:
    return PasswordHasher(rounds=4)  # the minimum cost: real bcrypt, a fraction of the time


@pytest.fixture
def bearer(access_tokens):
    """Authorization header for a user id: bearer(7), or bearer(7, scopes=("reservations:read",))."""

    def make(user_id: int, scopes: tuple[str, ...] = SCOPES_BY_ROLE[UserRole.CUSTOMER]) -> dict[str, str]:
        return {"Authorization": f"Bearer {access_tokens.issue(format_id(USER, user_id), scopes)}"}

    return make


@pytest.fixture
def auth_overrides(access_tokens, password_hasher) -> Iterator[None]:
    app.dependency_overrides[get_access_tokens] = lambda: access_tokens
    app.dependency_overrides[get_password_hasher] = lambda: password_hasher
    yield
    app.dependency_overrides.pop(get_access_tokens, None)
    app.dependency_overrides.pop(get_password_hasher, None)


@pytest.fixture
def client(uow_factory: UnitOfWorkFactory, auth_overrides) -> Iterator[TestClient]:
    """API client wired to the test database. Each use case gets its own unit of work."""
    app.dependency_overrides[get_uow_factory] = lambda: uow_factory
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(get_uow_factory, None)


@pytest.fixture
def api_client(auth_overrides) -> Iterator[TestClient]:
    """API client for tests that don't touch the database."""
    with TestClient(app) as c:
        yield c
