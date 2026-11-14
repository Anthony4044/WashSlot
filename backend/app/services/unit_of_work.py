"""The seam the service layer depends on: what is stored, never how.

Implemented by app.data.unit_of_work.SqlAlchemyUnitOfWork (Postgres) and
app.data.memory.MemoryUnitOfWork (tests). Services receive a factory: `with self.uow_factory() as uow:`.
"""
from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from app.domain.laundromat import Laundromat
from app.domain.slot import MachineSlot, SlotDetails
from app.domain.user import User


class SlotRepository(Protocol):
    def now(self) -> datetime: ...
    def get(self, slot_id: int, *, lock: bool = False) -> MachineSlot | None: ...
    def get_for_reservation(self, reservation_id: int, *, lock: bool = False) -> MachineSlot | None: ...
    def save(self, slot: MachineSlot) -> None: ...

    def details(self, slot_id: int) -> SlotDetails | None:
        """Read-only: the slot's laundromat, machine and times, for building responses."""
        ...


class LaundromatRepository(Protocol):
    def list_all(self) -> list[Laundromat]:
        """Every laundromat, ordered by name."""
        ...


class UserRepository(Protocol):
    def get_by_email(self, email: str) -> User | None: ...

    def add(self, user: User) -> User | None:
        """Insert a new user and return it with its id, or None if the email is already taken."""
        ...


class UnitOfWork(Protocol):
    slots: SlotRepository
    laundromats: LaundromatRepository
    users: UserRepository

    def __enter__(self) -> "UnitOfWork": ...
    def __exit__(self, exc_type, exc, tb) -> None: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...


UnitOfWorkFactory = Callable[[], UnitOfWork]
