"""The seam the service layer depends on: what is stored, never how.

Implemented by app.data.unit_of_work.SqlAlchemyUnitOfWork (Postgres) and
app.data.memory.MemoryUnitOfWork (tests). Services receive a factory: `with self.uow_factory() as uow:`.
"""
from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from app.domain.availability import SlotAvailabilityRow
from app.domain.laundromat import Laundromat
from app.domain.slot import MachineSlot, Reservation, SlotDetails
from app.domain.user import User


class SlotRepository(Protocol):
    def now(self) -> datetime: ...
    def get(self, slot_id: int, *, lock: bool = False) -> MachineSlot | None: ...
    def get_for_reservation(self, reservation_id: int, *, lock: bool = False) -> MachineSlot | None: ...
    def save(self, slot: MachineSlot) -> None: ...

    def details(self, slot_id: int) -> SlotDetails | None:
        """Read-only: the slot's laundromat, machine and times, for building responses."""
        ...

    def list_for_user(self, user_id: int) -> list[tuple[Reservation, SlotDetails]]:
        """The caller's reservations with where/when, newest first (by id). Read model."""
        ...


class LaundromatRepository(Protocol):
    def list_all(self) -> list[Laundromat]:
        """Every laundromat, ordered by name."""
        ...

    def get(self, laundromat_id: int) -> Laundromat | None: ...

    def reservable_slots_for_day(
        self, laundromat_id: int, day_start: datetime, day_end: datetime
    ) -> list[SlotAvailabilityRow]:
        """One query: reservable machines and their slots starting in [day_start, day_end).

        `available` matches MachineSlot.is_available against the database clock.
        """
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
