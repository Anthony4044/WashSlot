"""Shared test fixtures. Three levels of test:

- domain tests:        plain objects, no fixtures, no database (tests/test_domain_*.py)
- service tests:       use cases against app.data.memory doubles (`memory_uow`)
- database / API tests: against TEST_DATABASE_URL (`db_engine`, `uow_factory`, `client`)
- conformance tests:   the running API checked against contract/openapi.yaml (tests/conformance/)

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

from app.api.deps import get_uow_factory
from app.core.config import get_settings, to_sqlalchemy_url
from app.data.database import make_engine, make_session_factory
from app.data.memory import MemoryUnitOfWork
from app.data.tables import Base
from app.data.unit_of_work import SqlAlchemyUnitOfWork
from app.main import app
from app.services.unit_of_work import UnitOfWorkFactory

BACKEND_DIR = Path(__file__).resolve().parents[1]


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
        conn.execute(text("DROP TABLE IF EXISTS alembic_version"))
        Base.metadata.drop_all(conn)
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


@pytest.fixture
def client(uow_factory: UnitOfWorkFactory) -> Iterator[TestClient]:
    """API client wired to the test database. Each use case gets its own unit of work."""
    app.dependency_overrides[get_uow_factory] = lambda: uow_factory
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(get_uow_factory, None)


@pytest.fixture
def api_client() -> Iterator[TestClient]:
    """API client for tests that don't touch the database."""
    with TestClient(app) as c:
        yield c
