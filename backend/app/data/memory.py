"""In-memory doubles for service-layer tests.

They copy on get and on save, exactly like the database does: a change you don't save is lost.
That keeps tests honest - a test that forgets to save fails here too, not only against Postgres.
"""
import copy
from dataclasses import replace
from datetime import UTC, datetime

from app.domain.availability import SlotAvailabilityRow
from app.domain.enums import MachineType
from app.domain.laundromat import Laundromat
from app.domain.slot import MachineSlot, SlotDetails
from app.domain.user import User


class MemorySlotRepository:
    def __init__(self, clock=lambda: datetime.now(UTC)):
        self._slots: dict[int, MachineSlot] = {}
        self._details: dict[int, SlotDetails] = {}
        self._next_reservation_id = 1
        self._clock = clock

    def now(self) -> datetime:
        return self._clock()

    def add(self, slot: MachineSlot, details: SlotDetails | None = None) -> None:
        """Test setup helper: put a slot in the store (with made-up details unless you pass some)."""
        self._slots[slot.id] = copy.deepcopy(slot)
        self._details[slot.id] = details or SlotDetails(
            slot_id=slot.id, laundromat_id=1, laundromat_name="Spin City", machine_id=slot.machine_id,
            machine_label=f"Washer {slot.machine_id}", machine_type=MachineType.WASHER,
            start_time=slot.start_time, end_time=slot.end_time)

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

    def details(self, slot_id: int) -> SlotDetails | None:
        return self._details.get(slot_id)


class MemoryUserRepository:
    def __init__(self):
        self._users: dict[int, User] = {}
        self._next_id = 1

    def get_by_email(self, email: str) -> User | None:
        found = next((u for u in self._users.values() if u.email == email), None)
        return replace(found) if found else None

    def add(self, user: User) -> User | None:
        if any(u.email == user.email for u in self._users.values()):
            return None  # the unique email constraint
        saved = replace(user, id=self._next_id)
        self._next_id += 1
        self._users[saved.id] = replace(saved)
        return saved


class MemoryLaundromatRepository:
    def __init__(self, slots: MemorySlotRepository | None = None):
        self._laundromats: dict[int, Laundromat] = {}
        self._slot_rows: list[SlotAvailabilityRow] = []
        self._slots = slots  # optional: derive availability from MemorySlotRepository

    def add(self, laundromat: Laundromat) -> Laundromat:
        """Test setup helper."""
        self._laundromats[laundromat.id] = laundromat
        return laundromat

    def add_slot_row(self, row: SlotAvailabilityRow) -> None:
        """Test setup helper for the browse read model."""
        self._slot_rows.append(row)

    def list_all(self) -> list[Laundromat]:
        return sorted(self._laundromats.values(), key=lambda lm: (lm.name, lm.id))

    def get(self, laundromat_id: int) -> Laundromat | None:
        return self._laundromats.get(laundromat_id)

    def reservable_slots_for_day(
        self, laundromat_id: int, day_start: datetime, day_end: datetime
    ) -> list[SlotAvailabilityRow]:
        rows = [
            row
            for row in self._slot_rows
            if day_start <= row.start_time < day_end
        ]
        if self._slots is not None:
            now = self._slots.now()
            rows = [
                SlotAvailabilityRow(
                    machine_id=row.machine_id,
                    machine_label=row.machine_label,
                    machine_type=row.machine_type,
                    slot_id=row.slot_id,
                    start_time=row.start_time,
                    end_time=row.end_time,
                    available=(
                        (slot := self._slots.get(row.slot_id)) is not None and slot.is_available(now)
                    ),
                )
                for row in rows
            ]
        return sorted(rows, key=lambda r: (r.machine_label, r.machine_id, r.start_time))


class MemoryUnitOfWork:
    """Same interface as SqlAlchemyUnitOfWork. Shares one store across units of work."""

    def __init__(
        self,
        slots: MemorySlotRepository | None = None,
        users: MemoryUserRepository | None = None,
        laundromats: MemoryLaundromatRepository | None = None,
    ):
        self.slots = slots or MemorySlotRepository()
        self.users = users or MemoryUserRepository()
        self.laundromats = laundromats or MemoryLaundromatRepository(self.slots)
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
