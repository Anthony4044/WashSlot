"""SQL repositories: the Data Mapper between rows and domain objects.

One aggregate, one repository: there is no ReservationRepository. Reservations are
loaded and saved through their slot, so every writer passes the same door - the slot row's lock.
"""
from dataclasses import replace
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.data.tables import LaundromatRow, MachineRow, MachineSlotRow, ReservationRow, UserRow
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
        """The database clock: the one authority for expiry decisions (proposal, section 5)."""
        return self.session.execute(select(func.now())).scalar_one()

    def get(self, slot_id: int, *, lock: bool = False) -> MachineSlot | None:
        """Load the whole aggregate. lock=True takes SELECT ... FOR UPDATE on the slot row,
        held until the unit of work ends, so concurrent writers to this slot queue up."""
        query = select(MachineSlotRow).where(MachineSlotRow.id == slot_id)
        if lock:
            query = query.with_for_update()
        row = self.session.execute(query).scalar_one_or_none()
        if row is None:
            return None
        reservations = self.session.execute(
            select(ReservationRow).where(ReservationRow.slot_id == slot_id).order_by(ReservationRow.id)
        ).scalars()
        return MachineSlot(
            id=row.id,
            machine_id=row.machine_id,
            start_time=row.start_time,
            end_time=row.end_time,
            reservations=[_to_domain(r) for r in reservations],
        )

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


class SqlUserRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_email(self, email: str) -> User | None:
        row = self.session.execute(select(UserRow).where(UserRow.email == email)).scalar_one_or_none()
        if row is None:
            return None
        return User(id=row.id, email=row.email, password_hash=row.password_hash, role=row.role)

    def add(self, user: User) -> User | None:
        """INSERT ... ON CONFLICT (email) DO NOTHING: of two sign-ups racing for one email,
        exactly one gets a row and the other gets None, with no error and no check-then-insert gap."""
        new_id = self.session.execute(
            insert(UserRow)
            .values(email=user.email, password_hash=user.password_hash, role=user.role)
            .on_conflict_do_nothing(index_elements=[UserRow.email])
            .returning(UserRow.id)
        ).scalar_one_or_none()
        return None if new_id is None else replace(user, id=new_id)
