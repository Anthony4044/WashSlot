from sqlalchemy import BigInteger, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.data.tables.base import Base, CreatedAtMixin


class IdempotencyRecordRow(CreatedAtMixin, Base):
    """The outcome of one attempt sent with an Idempotency-Key (US-5.2).

    Written in the SAME transaction as the hold, so the hold and its record are saved together or
    not at all. The primary key (user_id, key) is what makes a twin request lose: of two INSERTs with
    the same key, only one gets a row. Kept at least IDEMPOTENCY_RETENTION_HOURS (24), then swept.
    """

    __tablename__ = "idempotency_records"
    __table_args__ = (
        # The sweep's question: "which records are older than 24 hours?"
        Index("ix_idempotency_records_created_at", "created_at"),
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    endpoint: Mapped[str] = mapped_column(String(100), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)  # SHA-256, hex
    error_code: Mapped[str | None] = mapped_column(String(50))  # NULL: success, response_body holds it
    response_body: Mapped[dict | None] = mapped_column(JSONB)
