"""SQL repositories: the Data Mapper between rows and domain objects.

One aggregate, one repository: there is no ReservationRepository. Reservations are
loaded and saved through their slot, so every writer passes the same door - the slot row's lock.
"""
from dataclasses import replace
from datetime import datetime, timedelta

from sqlalchemy import and_, delete, exists, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.data.tables import (
    IdempotencyRecordRow,
    LaundromatRow,
    MachineRow,
    MachineSlotRow,
    NotificationOutboxRow,
    ReservationRow,
    UserRow,
)
from app.domain.availability import SlotAvailabilityRow
from app.domain.enums import OutboxStatus, ReservationStatus
from app.domain.idempotency import IdempotencyRecord
from app.domain.laundromat import BOOKING_STATUSES, Laundromat, TodayBooking
from app.domain.machine import Machine
from app.domain.notification import CLAIM_LEASE, OutboxMessage
from app.domain.slot import MachineSlot, Reservation, SlotDetails
from app.domain.user import User

_RESERVATION_FIELDS = (
    "slot_id",
    "user_id",
    "status",
    "confirmation_email",
    "expires_at",
    "confirmed_at",
    "cancelled_at",
    "checked_in_at",
)


def _to_domain(row: ReservationRow) -> Reservation:
    return Reservation(id=row.id, created_at=row.created_at, **{f: getattr(row, f) for f in _RESERVATION_FIELDS})


class SqlSlotRepository:
    def __init__(self, session: Session):
        self.session = session

    def now(self) -> datetime:
        """Read the database clock after taking any locks, even if the transaction had to wait."""
        return self.session.execute(select(func.statement_timestamp())).scalar_one()

    def get(self, slot_id: int, *, lock: bool = False) -> MachineSlot | None:
        """Load the whole aggregate. lock=True takes SELECT ... FOR UPDATE on the slot row,
        held until the unit of work ends, so concurrent writers to this slot queue up.

        The machine's `reservable` flag comes along (US-7.1: no new holds on a walk-in-only machine).
        `FOR UPDATE OF machine_slots` locks only the slot row, never the machine row, so holds on
        other slots of the same machine don't wait for each other.
        """
        query = (
            select(MachineSlotRow, MachineRow.reservable)
            .join(MachineRow, MachineRow.id == MachineSlotRow.machine_id)
            .where(MachineSlotRow.id == slot_id)
        )
        if lock:
            query = query.with_for_update(of=MachineSlotRow)
        found = self.session.execute(query).one_or_none()
        if found is None:
            return None
        row, reservable = found
        reservations = self.session.execute(
            select(ReservationRow).where(ReservationRow.slot_id == slot_id).order_by(ReservationRow.id)
        ).scalars()
        return MachineSlot(
            id=row.id,
            machine_id=row.machine_id,
            start_time=row.start_time,
            end_time=row.end_time,
            reservations=[_to_domain(r) for r in reservations],
            machine_reservable=reservable,
        )

    def create_many(self, new_slots: list[tuple[int, datetime, datetime]]) -> int:
        """Operator tool (US-7.1): insert (machine_id, start, end) slots; returns how many were new.

            INSERT INTO machine_slots (machine_id, start_time, end_time) VALUES (...), (...)
            ON CONFLICT (machine_id, start_time) DO NOTHING RETURNING id

        The unique constraint uq_machine_slots_machine_start decides what already exists, inside the
        one statement: no check-then-insert gap, and repeating the request creates nothing more.
        """
        if not new_slots:
            return 0
        inserted = self.session.execute(
            insert(MachineSlotRow)
            .values([{"machine_id": m, "start_time": s, "end_time": e} for m, s, e in new_slots])
            .on_conflict_do_nothing(index_elements=[MachineSlotRow.machine_id, MachineSlotRow.start_time])
            .returning(MachineSlotRow.id)
        ).scalars().all()
        return len(inserted)

    def get_for_reservation(self, reservation_id: int, *, lock: bool = False) -> MachineSlot | None:
        """Load the aggregate that owns a reservation (locking the ROOT, never just the child)."""
        slot_id = self.session.execute(
            select(ReservationRow.slot_id).where(ReservationRow.id == reservation_id)
        ).scalar_one_or_none()
        return None if slot_id is None else self.get(slot_id, lock=lock)

    def save(self, slot: MachineSlot) -> None:
        """Write the aggregate's reservations back: insert new ones, update changed ones."""
        for r in slot.reservations:
            values = {f: getattr(r, f) for f in _RESERVATION_FIELDS}
            if r.id is None:
                row = ReservationRow(**values)
                self.session.add(row)
                self.session.flush()  # assigns the id (and created_at) now
                r.id, r.created_at = row.id, row.created_at
            else:
                row = self.session.get(ReservationRow, r.id)
                for field, value in values.items():
                    setattr(row, field, value)
        self.session.flush()

    def expire_all_stale_holds(self) -> int:
        """Worker job (US-5.1): one UPDATE for the whole table, using the database clock.

            UPDATE reservations SET status = 'EXPIRED'
            WHERE status = 'HELD' AND expires_at <= now()

        Same rule as Reservation.expire_if_stale. Safe next to a confirm: Postgres re-checks the
        WHERE on a row another transaction just changed, so a hold confirmed in time stays CONFIRMED.
        """
        result = self.session.execute(
            update(ReservationRow)
            .where(ReservationRow.status == ReservationStatus.HELD, ReservationRow.expires_at <= func.now())
            .values(status=ReservationStatus.EXPIRED)
        )
        return result.rowcount

    def no_show_candidate_ids(self, started_by: datetime) -> list[int]:
        return list(self.session.scalars(
            select(MachineSlotRow.id)
            .join(ReservationRow, ReservationRow.slot_id == MachineSlotRow.id)
            .where(
                MachineSlotRow.start_time <= started_by,
                ReservationRow.status == ReservationStatus.CONFIRMED,
                ReservationRow.checked_in_at.is_(None),
            )
            .order_by(MachineSlotRow.id)
        ))

    def details(self, slot_id: int) -> SlotDetails | None:
        """One query joining slot -> machine -> laundromat. No lock: nothing is decided on it."""
        row = self.session.execute(
            select(MachineSlotRow, MachineRow, LaundromatRow)
            .join(MachineRow, MachineRow.id == MachineSlotRow.machine_id)
            .join(LaundromatRow, LaundromatRow.id == MachineRow.laundromat_id)
            .where(MachineSlotRow.id == slot_id)
        ).one_or_none()
        if row is None:
            return None
        slot, machine, laundromat = row
        return SlotDetails(slot_id=slot.id, laundromat_id=laundromat.id, laundromat_name=laundromat.name,
                           machine_id=machine.id, machine_label=machine.label, machine_type=machine.type,
                           start_time=slot.start_time, end_time=slot.end_time)

    def list_for_user(self, user_id: int) -> list[tuple[Reservation, SlotDetails]]:
        """One query: the caller's reservations with where/when, newest id first."""
        rows = self.session.execute(
            select(ReservationRow, MachineSlotRow, MachineRow, LaundromatRow)
            .join(MachineSlotRow, MachineSlotRow.id == ReservationRow.slot_id)
            .join(MachineRow, MachineRow.id == MachineSlotRow.machine_id)
            .join(LaundromatRow, LaundromatRow.id == MachineRow.laundromat_id)
            .where(ReservationRow.user_id == user_id)
            .order_by(ReservationRow.id.desc())
        ).all()
        return [
            (
                _to_domain(reservation),
                SlotDetails(
                    slot_id=slot.id,
                    laundromat_id=laundromat.id,
                    laundromat_name=laundromat.name,
                    machine_id=machine.id,
                    machine_label=machine.label,
                    machine_type=machine.type,
                    start_time=slot.start_time,
                    end_time=slot.end_time,
                ),
            )
            for reservation, slot, machine, laundromat in rows
        ]


def _laundromat(row: LaundromatRow) -> Laundromat:
    return Laundromat(id=row.id, name=row.name, address=row.address, timezone=row.timezone,
                      operator_id=row.operator_id)


class SqlLaundromatRepository:
    """Browse queries over laundromats (read model; no aggregate writes)."""

    def __init__(self, session: Session):
        self.session = session

    def list_all(self) -> list[Laundromat]:
        rows = self.session.scalars(select(LaundromatRow).order_by(LaundromatRow.name, LaundromatRow.id)).all()
        return [_laundromat(row) for row in rows]

    def list_for_operator(self, user_id: int) -> list[Laundromat]:
        """The laundromats this user operates, by name (US-7.1)."""
        rows = self.session.scalars(
            select(LaundromatRow)
            .where(LaundromatRow.operator_id == user_id)
            .order_by(LaundromatRow.name, LaundromatRow.id)
        ).all()
        return [_laundromat(row) for row in rows]

    def get(self, laundromat_id: int) -> Laundromat | None:
        row = self.session.get(LaundromatRow, laundromat_id)
        return None if row is None else _laundromat(row)

    def bookings_for_day(self, laundromat_id: int, day_start: datetime, day_end: datetime) -> list[TodayBooking]:
        rows = self.session.execute(
            select(
                ReservationRow.id,
                MachineRow.label,
                MachineSlotRow.start_time,
                MachineSlotRow.end_time,
                UserRow.email,
                ReservationRow.status,
                ReservationRow.checked_in_at,
            )
            .select_from(ReservationRow)
            .join(MachineSlotRow, MachineSlotRow.id == ReservationRow.slot_id)
            .join(MachineRow, MachineRow.id == MachineSlotRow.machine_id)
            .join(UserRow, UserRow.id == ReservationRow.user_id)
            .where(
                MachineRow.laundromat_id == laundromat_id,
                MachineSlotRow.start_time >= day_start,
                MachineSlotRow.start_time < day_end,
                ReservationRow.status.in_(BOOKING_STATUSES),
            )
            .order_by(MachineSlotRow.start_time, MachineRow.label, ReservationRow.id)
        )
        return [TodayBooking(*row) for row in rows]

    def reservable_slots_for_day(
        self, laundromat_id: int, day_start: datetime, day_end: datetime
    ) -> list[SlotAvailabilityRow]:
        """One SQL query, no N+1. Availability matches MachineSlot.is_available(database now)."""
        taken = exists(
            select(ReservationRow.id).where(
                ReservationRow.slot_id == MachineSlotRow.id,
                or_(
                    ReservationRow.status == ReservationStatus.CONFIRMED,
                    and_(
                        ReservationRow.status == ReservationStatus.HELD,
                        ReservationRow.expires_at > func.now(),
                    ),
                ),
            )
        )
        still_in_future = MachineSlotRow.start_time > func.now()
        rows = self.session.execute(
            select(
                MachineRow.id,
                MachineRow.label,
                MachineRow.type,
                MachineSlotRow.id,
                MachineSlotRow.start_time,
                MachineSlotRow.end_time,
                taken.label("taken"),
                still_in_future.label("future"),
            )
            .join(MachineSlotRow, MachineSlotRow.machine_id == MachineRow.id)
            .where(
                MachineRow.laundromat_id == laundromat_id,
                MachineRow.reservable.is_(True),
                MachineSlotRow.start_time >= day_start,
                MachineSlotRow.start_time < day_end,
            )
            .order_by(MachineRow.label, MachineRow.id, MachineSlotRow.start_time)
        ).all()
        return [
            SlotAvailabilityRow(
                machine_id=machine_id,
                machine_label=label,
                machine_type=machine_type,
                slot_id=slot_id,
                start_time=start_time,
                end_time=end_time,
                # Matches MachineSlot.is_available: not taken AND not started yet.
                available=(not taken_flag) and bool(future_flag),
            )
            for machine_id, label, machine_type, slot_id, start_time, end_time, taken_flag, future_flag in rows
        ]


class SqlUserRepository:
    """Repository + Data Mapper for users.

    The service asks for domain objects ("the user with this email") and gets a User back, never a
    UserRow, so the layers above never learn that a database exists. All the SQL lives here. It only
    offers the two operations its callers need: no generic get/save/delete/list.
    """

    def __init__(self, session: Session):
        self.session = session  # shared with the unit of work, so everything commits together

    def get_by_email(self, email: str) -> User | None:
        """Expects an already-normalized (lower-case) email: the domain's normalize_email decides that."""
        row = self.session.execute(select(UserRow).where(UserRow.email == email)).scalar_one_or_none()
        if row is None:
            return None
        return User(id=row.id, email=row.email, password_hash=row.password_hash, role=row.role)  # row -> domain

    def add(self, user: User) -> User | None:
        """INSERT ... ON CONFLICT (email) DO NOTHING: of two sign-ups racing for one email,
        exactly one gets a row and the other gets None, with no error and no check-then-insert gap.

        Why not "SELECT first, INSERT if free"? That is a check-then-act race: two
        requests both SELECT, both see the email free, and both INSERT. Here the database's unique
        constraint (uq_users_email) decides, inside the one INSERT statement, so there is no gap."""
        new_id = self.session.execute(
            insert(UserRow)
            .values(email=user.email, password_hash=user.password_hash, role=user.role)
            .on_conflict_do_nothing(index_elements=[UserRow.email])
            .returning(UserRow.id)
        ).scalar_one_or_none()
        return None if new_id is None else replace(user, id=new_id)


_OUTBOX_FIELDS = (
    "reservation_id",
    "laundromat_id",
    "type",
    "payload",
    "status",
    "attempts",
    "next_attempt_at",
    "last_error",
    "correlation_id",
    "sent_at",
)


class SqlOutboxRepository:
    """The notification outbox (US-6.1). Messages are written by confirm and sent by the worker."""

    def __init__(self, session: Session):
        self.session = session

    def add(self, message: OutboxMessage) -> None:
        row = NotificationOutboxRow(**{f: getattr(message, f) for f in _OUTBOX_FIELDS})
        self.session.add(row)
        self.session.flush()  # assigns the id now
        message.id, message.created_at = row.id, row.created_at

    def claim_next(self) -> OutboxMessage | None:
        """Take the oldest due PENDING message for this worker:

            SELECT ... FROM notification_outbox
            WHERE status = 'PENDING' AND next_attempt_at <= now()
            ORDER BY next_attempt_at, id LIMIT 1
            FOR UPDATE SKIP LOCKED

        SKIP LOCKED: if another worker is claiming that row right now, skip it instead of waiting.
        Then we push next_attempt_at forward (the lease) and the unit of work commits, so the
        email itself is sent OUTSIDE any transaction.
        """
        row = self.session.execute(
            select(NotificationOutboxRow)
            .where(
                NotificationOutboxRow.status == OutboxStatus.PENDING,
                NotificationOutboxRow.next_attempt_at <= func.now(),
            )
            .order_by(NotificationOutboxRow.next_attempt_at, NotificationOutboxRow.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        ).scalar_one_or_none()
        if row is None:
            return None
        now = self.session.execute(select(func.now())).scalar_one()  # the database clock
        row.next_attempt_at = now + CLAIM_LEASE
        self.session.flush()
        return _message(row)

    def save(self, message: OutboxMessage) -> None:
        row = self.session.get(NotificationOutboxRow, message.id)
        for f in _OUTBOX_FIELDS:
            setattr(row, f, getattr(message, f))
        self.session.flush()

    def get(self, message_id: int, *, lock: bool = False) -> OutboxMessage | None:
        """One message. lock=True adds FOR UPDATE: a second retry of the same email waits for the
        first to commit, then reads PENDING and changes nothing (US-7.3)."""
        query = select(NotificationOutboxRow).where(NotificationOutboxRow.id == message_id)
        if lock:
            query = query.with_for_update()
        row = self.session.execute(query).scalar_one_or_none()
        return None if row is None else _message(row)

    def list_for_laundromats(self, laundromat_ids: list[int], status: OutboxStatus | None,
                             limit: int) -> list[OutboxMessage]:
        """The operator's view (US-7.3): these laundromats' messages, newest first, at most `limit`."""
        if not laundromat_ids:
            return []
        query = select(NotificationOutboxRow).where(NotificationOutboxRow.laundromat_id.in_(laundromat_ids))
        if status is not None:
            query = query.where(NotificationOutboxRow.status == status)
        query = query.order_by(NotificationOutboxRow.created_at.desc(), NotificationOutboxRow.id.desc()).limit(limit)
        return [_message(row) for row in self.session.scalars(query)]


def _message(row: NotificationOutboxRow) -> OutboxMessage:
    return OutboxMessage(id=row.id, created_at=row.created_at, **{f: getattr(row, f) for f in _OUTBOX_FIELDS})


_IDEMPOTENCY_FIELDS = ("user_id", "key", "endpoint", "request_hash", "error_code", "response_body")


class SqlIdempotencyRepository:
    """Stored outcomes of Idempotency-Key attempts (US-5.2). Same session as the hold, so they commit together."""

    def __init__(self, session: Session):
        self.session = session

    def get(self, user_id: int, key: str) -> IdempotencyRecord | None:
        row = self.session.get(IdempotencyRecordRow, (user_id, key))
        if row is None:
            return None
        return IdempotencyRecord(created_at=row.created_at, **{f: getattr(row, f) for f in _IDEMPOTENCY_FIELDS})

    def add(self, record: IdempotencyRecord) -> bool:
        """INSERT ... ON CONFLICT (user_id, key) DO NOTHING RETURNING user_id.

        If a twin request inserted the same key first, Postgres makes this INSERT wait until the twin
        commits, then inserts nothing: 0 rows, False. Like SqlUserRepository.add, the database's key
        decides inside one statement, so there is no check-then-insert gap.
        """
        inserted = self.session.execute(
            insert(IdempotencyRecordRow)
            .values(**{f: getattr(record, f) for f in _IDEMPOTENCY_FIELDS})
            .on_conflict_do_nothing(index_elements=[IdempotencyRecordRow.user_id, IdempotencyRecordRow.key])
            .returning(IdempotencyRecordRow.user_id)
        ).scalar_one_or_none()
        return inserted is not None

    def delete_older_than(self, hours: int) -> int:
        """DELETE FROM idempotency_records WHERE created_at < now() - <hours> hours.

        The database clock, never the worker's: a record younger than `hours` is never deleted.
        """
        result = self.session.execute(
            delete(IdempotencyRecordRow).where(IdempotencyRecordRow.created_at < func.now() - timedelta(hours=hours))
        )
        return result.rowcount


class SqlMachineRepository:
    """Machines as the operator manages them (US-7.1)."""

    def __init__(self, session: Session):
        self.session = session

    def list_for_laundromat(self, laundromat_id: int) -> list[Machine]:
        rows = self.session.scalars(
            select(MachineRow)
            .where(MachineRow.laundromat_id == laundromat_id)
            .order_by(MachineRow.label, MachineRow.id)
        ).all()
        return [_machine(row) for row in rows]

    def get(self, machine_id: int) -> Machine | None:
        row = self.session.get(MachineRow, machine_id)
        return None if row is None else _machine(row)

    def save(self, machine: Machine) -> None:
        """Write back what an operator can change: the reservable switch."""
        row = self.session.get(MachineRow, machine.id)
        row.reservable = machine.reservable
        self.session.flush()


def _machine(row: MachineRow) -> Machine:
    return Machine(id=row.id, laundromat_id=row.laundromat_id, label=row.label, type=row.type,
                   reservable=row.reservable)
