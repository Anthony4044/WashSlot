"""SQLAlchemy row classes. Import every one here so Alembic and tests see the full schema."""
from app.data.tables.base import Base
from app.data.tables.idempotency import IdempotencyRecordRow
from app.data.tables.laundromat import LaundromatRow
from app.data.tables.machine import MachineRow
from app.data.tables.machine_slot import MachineSlotRow
from app.data.tables.notification import NotificationOutboxRow
from app.data.tables.reservation import ReservationRow
from app.data.tables.user import UserRow

__all__ = [
    "Base", "IdempotencyRecordRow", "LaundromatRow", "MachineRow", "MachineSlotRow", "NotificationOutboxRow",
    "ReservationRow", "UserRow",
]
