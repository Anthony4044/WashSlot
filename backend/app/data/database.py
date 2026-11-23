"""Database engine and session factory."""
from functools import lru_cache

from sqlalchemy import Engine, create_engine, pool
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings, to_sqlalchemy_url


def make_engine(url: str) -> Engine:
    # pool_pre_ping: Neon suspends idle databases, so check a pooled connection before using it.
    return create_engine(to_sqlalchemy_url(url), pool_pre_ping=True)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


@lru_cache
def get_engine() -> Engine:
    url = get_settings().database_url
    if not url:
        raise RuntimeError("DATABASE_URL is not set. Copy backend/.env.example to backend/.env.")
    return make_engine(url)


@lru_cache
def _get_probe_engine(url: str) -> Engine:
    return create_engine(to_sqlalchemy_url(url), poolclass=pool.NullPool, connect_args={"connect_timeout": 3})


def postgres_is_ready() -> bool:
    """Probe a fresh connection with a shorter timeout than the application's database operations."""
    url = get_settings().database_url
    if not url:
        return False
    try:
        with _get_probe_engine(url).connect() as connection:
            connection.exec_driver_sql("SELECT 1")
    except (SQLAlchemyError, ValueError):
        return False
    return True


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return make_session_factory(get_engine())
