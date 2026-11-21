from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Identity, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.data.tables.base import Base, CreatedAtMixin
from app.domain.enums import OutboxStatus


class NotificationOutboxRow(CreatedAtMixin, Base):
    """One email we owe a customer (US-6.1). Written by confirm, sent by the worker.

    laundromat_id lets an operator see only their own laundromat's failed emails (US-7.3).
    """

    __tablename__ = "notification_outbox"
    __table_args__ = (
        # The worker's question: "which PENDING messages are due now?"
        Index("ix_notification_outbox_status_next_attempt_at", "status", "next_attempt_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    reservation_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("reservations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    laundromat_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("laundromats.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[OutboxStatus] = mapped_column(Enum(OutboxStatus, name="outbox_status"), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text)
    correlation_id: Mapped[str | None] = mapped_column(String(64))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
