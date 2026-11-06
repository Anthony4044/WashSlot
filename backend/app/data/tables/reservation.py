from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Identity,
    Index,
    String,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.data.tables.base import Base, CreatedAtMixin
from app.domain.enums import ReservationStatus


class ReservationRow(CreatedAtMixin, Base):
    """Row for a hold (HELD) and, once confirmed, the reservation.

    Safety net: the partial unique index allows at most one HELD/CONFIRMED row per slot.
    The slot row lock is the main protection; this index catches any bug in it.
    """

    __tablename__ = "reservations"
    __table_args__ = (
        Index(
            "uq_reservations_active_slot",
            "slot_id",
            unique=True,
            postgresql_where=text("status IN ('HELD', 'CONFIRMED')"),
        ),
        Index("ix_reservations_status_expires_at", "status", "expires_at"),
        CheckConstraint("status <> 'HELD' OR expires_at IS NOT NULL", name="held_has_expiry"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    slot_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("machine_slots.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    status: Mapped[ReservationStatus] = mapped_column(
        Enum(ReservationStatus, name="reservation_status"), nullable=False
    )
    confirmation_email: Mapped[str] = mapped_column(String(320), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # set while HELD
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    checked_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
