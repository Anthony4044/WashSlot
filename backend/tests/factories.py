"""Helpers that put rows straight into the test database (arrange step of DB tests)."""
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.data.tables import LaundromatRow, MachineRow, MachineSlotRow, ReservationRow, UserRow
from app.domain.enums import MachineType, ReservationStatus

START = datetime(2026, 11, 20, 23, 0, tzinfo=UTC)


def make_user(db: Session, email: str = "a@example.com") -> UserRow:
    user = UserRow(email=email, password_hash="x")
    db.add(user)
    db.flush()
    return user


def make_slot(db: Session, start: datetime = START, label: str = "Washer 4") -> MachineSlotRow:
    laundromat = LaundromatRow(name="Spin City", address="1 Main St")
    db.add(laundromat)
    db.flush()
    machine = MachineRow(laundromat_id=laundromat.id, label=label, type=MachineType.WASHER, reservable=True)
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
