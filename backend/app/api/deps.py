"""Dependency wiring: the one place that picks concrete implementations (the composition root).

Routes ask for a unit-of-work factory and hand it to a service; tests override get_uow_factory.
"""
from app.data.database import get_session_factory
from app.data.unit_of_work import SqlAlchemyUnitOfWork
from app.services.unit_of_work import UnitOfWorkFactory


def get_uow_factory() -> UnitOfWorkFactory:
    session_factory = get_session_factory()
    return lambda: SqlAlchemyUnitOfWork(session_factory)
