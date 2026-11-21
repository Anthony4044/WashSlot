"""Helpers that put rows straight into the test database (arrange step of DB tests)."""
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.data.tables import LaundromatRow, MachineRow, MachineSlotRow, ReservationRow, UserRow
from app.domain.enums import MachineType, ReservationStatus

# A week from today at 18:00 in Toronto. It is always in the future, so the slot can still be booked
# (a fixed date would make the tests fail once that date has passed).
TORONTO = ZoneInfo("America/Toronto")
START = datetime.combine(date.today() + timedelta(days=7), time(18, 0), tzinfo=TORONTO).astimezone(UTC)


def make_user(db: Session, email: str = "a@example.com") -> UserRow:
    user = UserRow(email=email, password_hash="x")
    db.add(user)
    db.flush()
    return user


def make_slot(
    db: Session,
    start: datetime = START,
    label: str = "Washer 4",
    *,
    laundromat: LaundromatRow | None = None,
    reservable: bool = True,
) -> MachineSlotRow:
    if laundromat is None:
        laundromat = LaundromatRow(name="Spin City", address="1 Main St")
        db.add(laundromat)
        db.flush()
    machine = MachineRow(
        laundromat_id=laundromat.id, label=label, type=MachineType.WASHER, reservable=reservable
    )
    db.add(machine)
    db.flush()
    slot = MachineSlotRow(machine_id=machine.id, start_time=start, end_time=start + timedelta(hours=1))
    db.add(slot)
    db.flush()
    return slot


def make_reservation(db: Session, user: UserRow, slot: MachineSlotRow,
                     status: ReservationStatus = ReservationStatus.HELD,
                     expires_at: datetime | None = None) -> ReservationRow:
    row = ReservationRow(slot_id=slot.id, user_id=user.id, status=status, confirmation_email=user.email,
                         expires_at=expires_at or datetime.now(UTC) + timedelta(minutes=10))
    db.add(row)
    db.flush()
    return row
