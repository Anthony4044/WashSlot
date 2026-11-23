"""In-memory doubles for service-layer tests.

They copy on get and on save, exactly like the database does: a change you don't save is lost.
That keeps tests honest - a test that forgets to save fails here too, not only against Postgres.
"""
import copy
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from app.domain.availability import SlotAvailabilityRow
from app.domain.enums import MachineType, OutboxStatus, ReservationStatus
from app.domain.idempotency import IdempotencyRecord
from app.domain.laundromat import BOOKING_STATUSES, Laundromat, TodayBooking
from app.domain.machine import Machine
from app.domain.notification import CLAIM_LEASE, OutboxMessage
from app.domain.slot import MachineSlot, Reservation, SlotDetails
from app.domain.user import User


class MemorySlotRepository:
    def __init__(self, clock=lambda: datetime.now(UTC)):
        self._slots: dict[int, MachineSlot] = {}
        self._details: dict[int, SlotDetails] = {}
        self._next_reservation_id = 1
        self._clock = clock
        self.machines: MemoryMachineRepository | None = None  # set by MemoryUnitOfWork

    def now(self) -> datetime:
        return self._clock()

    def add(self, slot: MachineSlot, details: SlotDetails | None = None) -> None:
        """Test setup helper: put a slot in the store (with made-up details unless you pass some)."""
        self._slots[slot.id] = copy.deepcopy(slot)
        self._details[slot.id] = details or SlotDetails(
            slot_id=slot.id, laundromat_id=1, laundromat_name="Spin City", machine_id=slot.machine_id,
            machine_label=f"Washer {slot.machine_id}", machine_type=MachineType.WASHER,
            start_time=slot.start_time, end_time=slot.end_time)

    def all_slots(self) -> list[MachineSlot]:
        """Test helper: every stored slot, by id."""
        return [copy.deepcopy(self._slots[i]) for i in sorted(self._slots)]

    def get(self, slot_id: int, *, lock: bool = False) -> MachineSlot | None:
        slot = self._slots.get(slot_id)
        return self._with_machine(copy.deepcopy(slot)) if slot else None

    def get_for_reservation(self, reservation_id: int, *, lock: bool = False) -> MachineSlot | None:
        for slot in self._slots.values():
            if any(r.id == reservation_id for r in slot.reservations):
                return self._with_machine(copy.deepcopy(slot))
        return None

    def _with_machine(self, slot: MachineSlot) -> MachineSlot:
        """Like the SQL join: the machine's reservable switch comes along, when the machine is known."""
        machine = self.machines.get(slot.machine_id) if self.machines else None
        if machine is not None:
            slot.machine_reservable = machine.reservable
        return slot

    def create_many(self, new_slots: list[tuple[int, datetime, datetime]]) -> int:
        """Same as the SQL INSERT ... ON CONFLICT (machine_id, start_time) DO NOTHING."""
        taken = {(s.machine_id, s.start_time) for s in self._slots.values()}
        added = 0
        for machine_id, start, end in new_slots:
            if (machine_id, start) in taken:
                continue
            self.add(MachineSlot(id=max(self._slots, default=0) + 1, machine_id=machine_id,
                                 start_time=start, end_time=end))
            taken.add((machine_id, start))
            added += 1
        return added

    def save(self, slot: MachineSlot) -> None:
        for r in slot.reservations:
            if r.id is None:
                r.id = self._next_reservation_id
                r.created_at = self._clock()
                self._next_reservation_id += 1
        self._slots[slot.id] = copy.deepcopy(slot)

    def scheduled_machine_ids(self, machine_ids: list[int], start: datetime, end: datetime) -> set[int]:
        return {
            slot.machine_id for slot in self._slots.values()
            if slot.machine_id in machine_ids and slot.start_time < end and slot.end_time > start
        }

    def expire_all_stale_holds(self) -> int:
        """Same as the SQL UPDATE, using the domain rule on every reservation."""
        now = self._clock()
        return sum(len(slot.expire_stale_holds(now)) for slot in self._slots.values())

    def no_show_candidate_ids(self, started_by: datetime) -> list[int]:
        return sorted(
            slot.id for slot in self._slots.values()
            if slot.start_time <= started_by and any(
                r.status == ReservationStatus.CONFIRMED and r.checked_in_at is None for r in slot.reservations
            )
        )

    def details(self, slot_id: int) -> SlotDetails | None:
        return self._details.get(slot_id)

    def list_for_user(self, user_id: int) -> list[tuple[Reservation, SlotDetails]]:
        """Newest first by reservation id. Pairs match SqlSlotRepository.list_for_user."""
        pairs: list[tuple[Reservation, SlotDetails]] = []
        for slot in self._slots.values():
            details = self._details.get(slot.id)
            if details is None:
                continue
            for r in slot.reservations:
                if r.user_id == user_id and r.id is not None:
                    pairs.append((copy.deepcopy(r), details))
        pairs.sort(key=lambda item: item[0].id or 0, reverse=True)
        return pairs

    def bookings_for_day(self, laundromat_id: int, day_start: datetime, day_end: datetime):
        for slot_id, slot in self._slots.items():
            details = self._details[slot_id]
            if details.laundromat_id == laundromat_id and day_start <= slot.start_time < day_end:
                for reservation in slot.reservations:
                    if reservation.status in BOOKING_STATUSES and reservation.id is not None:
                        yield reservation, details


class MemoryUserRepository:
    def __init__(self):
        self._users: dict[int, User] = {}
        self._next_id = 1

    def get_by_email(self, email: str) -> User | None:
        found = next((u for u in self._users.values() if u.email == email), None)
        return replace(found) if found else None

    def email_for(self, user_id: int) -> str:
        return self._users[user_id].email

    def add(self, user: User) -> User | None:
        if any(u.email == user.email for u in self._users.values()):
            return None  # the unique email constraint
        saved = replace(user, id=self._next_id)
        self._next_id += 1
        self._users[saved.id] = replace(saved)
        return saved


class MemoryLaundromatRepository:
    def __init__(self, slots: MemorySlotRepository | None = None, users: MemoryUserRepository | None = None):
        self._laundromats: dict[int, Laundromat] = {}
        self._slot_rows: list[SlotAvailabilityRow] = []
        self._slots = slots  # optional: derive availability from MemorySlotRepository
        self._users = users

    def add(self, laundromat: Laundromat) -> Laundromat:
        """Test setup helper."""
        self._laundromats[laundromat.id] = laundromat
        return laundromat

    def add_slot_row(self, row: SlotAvailabilityRow) -> None:
        """Test setup helper for the browse read model."""
        self._slot_rows.append(row)

    def list_all(self) -> list[Laundromat]:
        return sorted(self._laundromats.values(), key=lambda lm: (lm.name, lm.id))

    def list_for_operator(self, user_id: int) -> list[Laundromat]:
        return [lm for lm in self.list_all() if lm.operator_id == user_id]

    def get(self, laundromat_id: int) -> Laundromat | None:
        return self._laundromats.get(laundromat_id)

    def bookings_for_day(self, laundromat_id: int, day_start: datetime, day_end: datetime) -> list[TodayBooking]:
        if self._slots is None or self._users is None:
            return []
        bookings = [
            TodayBooking(
                reservation_id=reservation.id, machine_label=details.machine_label,
                start_time=details.start_time, end_time=details.end_time,
                customer_email=self._users.email_for(reservation.user_id),
                status=reservation.status, checked_in_at=reservation.checked_in_at,
            )
            for reservation, details in self._slots.bookings_for_day(laundromat_id, day_start, day_end)
        ]
        return sorted(bookings, key=lambda row: (row.start_time, row.machine_label, row.reservation_id))

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


class MemoryOutboxRepository:
    """Same behaviour as SqlOutboxRepository. Tests read `messages` to see what was written."""

    def __init__(self, clock):
        self.messages: dict[int, OutboxMessage] = {}
        self._next_id = 1
        self._clock = clock

    def add(self, message: OutboxMessage) -> None:
        message.id = self._next_id
        message.created_at = self._clock()
        self._next_id += 1
        self.messages[message.id] = copy.deepcopy(message)

    def claim_next(self) -> OutboxMessage | None:
        now = self._clock()
        due = [m for m in self.messages.values() if m.status == OutboxStatus.PENDING and m.next_attempt_at <= now]
        if not due:
            return None
        oldest = min(due, key=lambda m: (m.next_attempt_at, m.id))
        oldest.next_attempt_at = now + CLAIM_LEASE
        return copy.deepcopy(oldest)

    def save(self, message: OutboxMessage) -> None:
        self.messages[message.id] = copy.deepcopy(message)

    def get(self, message_id: int, *, lock: bool = False) -> OutboxMessage | None:
        message = self.messages.get(message_id)
        return copy.deepcopy(message) if message else None

    def list_for_laundromats(self, laundromat_ids: list[int], status: OutboxStatus | None,
                             limit: int) -> list[OutboxMessage]:
        mine = [m for m in self.messages.values()
                if m.laundromat_id in laundromat_ids and (status is None or m.status == status)]
        mine.sort(key=lambda m: (m.created_at, m.id), reverse=True)
        return [copy.deepcopy(m) for m in mine[:limit]]


class MemoryMachineRepository:
    """Same behaviour as SqlMachineRepository."""

    def __init__(self):
        self._machines: dict[int, Machine] = {}

    def add(self, machine: Machine) -> Machine:
        """Test setup helper."""
        self._machines[machine.id] = copy.deepcopy(machine)
        return machine

    def list_for_laundromat(self, laundromat_id: int, *, lock: bool = False) -> list[Machine]:
        found = [m for m in self._machines.values() if m.laundromat_id == laundromat_id]
        return [copy.deepcopy(m) for m in sorted(found, key=lambda m: (m.label, m.id))]

    def get(self, machine_id: int) -> Machine | None:
        machine = self._machines.get(machine_id)
        return copy.deepcopy(machine) if machine else None

    def save(self, machine: Machine) -> None:
        self._machines[machine.id] = copy.deepcopy(machine)


class MemoryIdempotencyRepository:
    """Same behaviour as SqlIdempotencyRepository. Tests read `records` to see what was stored."""

    def __init__(self, clock):
        self.records: dict[tuple[int, str], IdempotencyRecord] = {}
        self._clock = clock

    def get(self, user_id: int, key: str) -> IdempotencyRecord | None:
        record = self.records.get((user_id, key))
        return copy.deepcopy(record) if record else None

    def add(self, record: IdempotencyRecord) -> bool:
        if (record.user_id, record.key) in self.records:
            return False  # the primary key (user_id, key): ON CONFLICT DO NOTHING
        self.records[(record.user_id, record.key)] = copy.deepcopy(replace(record, created_at=self._clock()))
        return True

    def delete_older_than(self, hours: int) -> int:
        cutoff = self._clock() - timedelta(hours=hours)
        old = [k for k, r in self.records.items() if r.created_at < cutoff]
        for k in old:
            del self.records[k]
        return len(old)


class MemoryUnitOfWork:
    """Same interface as SqlAlchemyUnitOfWork. Shares one store across units of work.

    No real transactions: a write is kept even if the block later fails. So a test can't see a
    rollback here (the twin-request path of idempotency is tested on the real database).
    """

    def __init__(
        self,
        slots: MemorySlotRepository | None = None,
        users: MemoryUserRepository | None = None,
        laundromats: MemoryLaundromatRepository | None = None,
        outbox: MemoryOutboxRepository | None = None,
        idempotency: MemoryIdempotencyRepository | None = None,
        machines: MemoryMachineRepository | None = None,
    ):
        self.slots = slots or MemorySlotRepository()
        self.users = users or MemoryUserRepository()
        self.laundromats = laundromats or MemoryLaundromatRepository(self.slots, self.users)
        self.outbox = outbox or MemoryOutboxRepository(clock=self.slots.now)  # same clock as the slots
        self.idempotency = idempotency or MemoryIdempotencyRepository(clock=self.slots.now)
        self.machines = machines or MemoryMachineRepository()
        self.slots.machines = self.machines  # a slot reads its machine's reservable switch, like the SQL join
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
