from sqlalchemy import BigInteger, Boolean, Enum, ForeignKey, Identity, String, UniqueConstraint, false
from sqlalchemy.orm import Mapped, mapped_column

from app.data.tables.base import Base, CreatedAtMixin
from app.domain.enums import MachineType


class MachineRow(CreatedAtMixin, Base):
    __tablename__ = "machines"
    __table_args__ = (UniqueConstraint("laundromat_id", "label", name="uq_machines_laundromat_label"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    laundromat_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("laundromats.id", ondelete="CASCADE"), nullable=False, index=True
    )
    label: Mapped[str] = mapped_column(String(50), nullable=False)  # e.g. "Washer 4"
    type: Mapped[MachineType] = mapped_column(Enum(MachineType, name="machine_type"), nullable=False)
    # Operators opt machines in; the rest stay walk-in only.
    reservable: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=false())
