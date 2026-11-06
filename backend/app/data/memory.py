"""In-memory doubles for service-layer tests.

They copy on get and on save, exactly like the database does: a change you don't save is lost.
That keeps tests honest - a test that forgets to save fails here too, not only against Postgres.
"""
import copy
from datetime import UTC, datetime

from app.domain.slot import MachineSlot


class MemorySlotRepository:
    def __init__(self, clock=lambda: datetime.now(UTC)):
        self._slots: dict[int, MachineSlot] = {}
        self._next_reservation_id = 1
        self._clock = clock

    def now(self) -> datetime:
        return self._clock()

    def add(self, slot: MachineSlot) -> None:
        """Test setup helper: put a slot in the store."""
        self._slots[slot.id] = copy.deepcopy(slot)

    def get(self, slot_id: int, *, lock: bool = False) -> MachineSlot | None:
        slot = self._slots.get(slot_id)
        return copy.deepcopy(slot) if slot else None

    def get_for_reservation(self, reservation_id: int, *, lock: bool = False) -> MachineSlot | None:
        for slot in self._slots.values():
            if any(r.id == reservation_id for r in slot.reservations):
                return copy.deepcopy(slot)
        return None

    def save(self, slot: MachineSlot) -> None:
        for r in slot.reservations:
            if r.id is None:
                r.id = self._next_reservation_id
                r.created_at = self._clock()
                self._next_reservation_id += 1
        self._slots[slot.id] = copy.deepcopy(slot)


class MemoryUnitOfWork:
    """Same interface as SqlAlchemyUnitOfWork. Shares one store across units of work."""

    def __init__(self, slots: MemorySlotRepository | None = None):
        self.slots = slots or MemorySlotRepository()
        self.committed = False

    def __call__(self) -> "MemoryUnitOfWork":  # lets the instance act as its own factory
        return self

    def __enter__(self) -> "MemoryUnitOfWork":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc_type is None:
            self.commit()

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        pass
