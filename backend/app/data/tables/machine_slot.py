from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Identity, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.data.tables.base import Base, CreatedAtMixin


class MachineSlotRow(CreatedAtMixin, Base):
    """Row of the slot aggregate root. The hold service locks this row with SELECT ... FOR UPDATE."""

    __tablename__ = "machine_slots"
    __table_args__ = (
        UniqueConstraint("machine_id", "start_time", name="uq_machine_slots_machine_start"),
        CheckConstraint("end_time > start_time", name="end_after_start"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    machine_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("machines.id", ondelete="CASCADE"), nullable=False
    )
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
