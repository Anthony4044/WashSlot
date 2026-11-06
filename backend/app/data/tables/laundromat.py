from sqlalchemy import BigInteger, ForeignKey, Identity, String
from sqlalchemy.orm import Mapped, mapped_column

from app.data.tables.base import Base, CreatedAtMixin


class LaundromatRow(CreatedAtMixin, Base):
    __tablename__ = "laundromats"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    address: Mapped[str] = mapped_column(String(255), nullable=False)
    # Nullable so laundromats can be seeded before an operator account exists.
    operator_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    # Used to turn "?date=YYYY-MM-DD" into a time range and to show local times.
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, server_default="America/Toronto")
