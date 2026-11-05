"""The seam the service layer depends on: what is stored, never how.

Implemented by app.data.unit_of_work.SqlAlchemyUnitOfWork (Postgres) and
app.data.memory.MemoryUnitOfWork (tests). Services receive a factory: `with self.uow_factory() as uow:`.
"""
from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from app.domain.slot import MachineSlot


class SlotRepository(Protocol):
    def now(self) -> datetime: ...
    def get(self, slot_id: int, *, lock: bool = False) -> MachineSlot | None: ...
    def get_for_reservation(self, reservation_id: int, *, lock: bool = False) -> MachineSlot | None: ...
    def save(self, slot: MachineSlot) -> None: ...


class UnitOfWork(Protocol):
    slots: SlotRepository

    def __enter__(self) -> "UnitOfWork": ...
    def __exit__(self, exc_type, exc, tb) -> None: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...


UnitOfWorkFactory = Callable[[], UnitOfWork]
