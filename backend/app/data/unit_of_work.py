"""Unit of Work over a SQLAlchemy session.

One use case = one unit of work = one transaction. The service layer opens it:

    with self.uow_factory() as uow:              # BEGIN
        slot = uow.slots.get(slot_id, lock=True)  # SELECT ... FOR UPDATE
        ...                                      # domain rule
        uow.slots.save(slot)
                                                 # COMMIT on normal exit, ROLLBACK on exception

Keep it short: no external calls (email, payments) inside it.
"""
from sqlalchemy.orm import Session, sessionmaker

from app.data.repositories import SqlSlotRepository, SqlUserRepository


class SqlAlchemyUnitOfWork:
    def __init__(self, session_factory: sessionmaker[Session]):
        self._session_factory = session_factory

    def __enter__(self) -> "SqlAlchemyUnitOfWork":
        self.session = self._session_factory()
        self.slots = SqlSlotRepository(self.session)
        self.users = SqlUserRepository(self.session)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            if exc_type is None:
                self.session.commit()
            else:
                self.session.rollback()
        finally:
            self.session.close()

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()
