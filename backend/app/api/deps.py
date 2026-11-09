"""Dependency wiring: the one place that picks concrete implementations (the composition root).

Routes ask for a unit-of-work factory and hand it to a service; tests override get_uow_factory.
Tests also override get_access_tokens (throwaway keys) and get_password_hasher (fast bcrypt).
"""
from functools import lru_cache

from app.core.config import get_settings
from app.core.passwords import PasswordHasher
from app.core.tokens import AccessTokens
from app.data.database import get_session_factory
from app.data.unit_of_work import SqlAlchemyUnitOfWork
from app.services.unit_of_work import UnitOfWorkFactory


def get_uow_factory() -> UnitOfWorkFactory:
    session_factory = get_session_factory()
    return lambda: SqlAlchemyUnitOfWork(session_factory)


@lru_cache
def get_access_tokens() -> AccessTokens:
    """Loaded on first use, so the app starts before the keys exist (python scripts/generate_keys.py)."""
    return AccessTokens.from_settings(get_settings())


@lru_cache
def get_password_hasher() -> PasswordHasher:
    return PasswordHasher()
