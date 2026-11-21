"""notification_outbox: emails waiting to be sent by the worker (US-6.1).

Merge note: migration 0002 (idempotency_records, US-5.2) is not merged yet, so this one sits on
0001 for now. Whichever of the two PRs merges second changes the other's place in the chain:
0003's down_revision becomes "0002". Then `alembic heads` shows one head again.

Revision ID: 0003
Revises: 0001
Create Date: 2026-11-21
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0001"  # becomes "0002" once US-5.2 is merged
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

outbox_status = sa.Enum("PENDING", "SENT", "FAILED", name="outbox_status")


def upgrade() -> None:
    op.create_table(
        "notification_outbox",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("reservation_id", sa.BigInteger(), nullable=False),
        sa.Column("laundromat_id", sa.BigInteger(), nullable=False),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("status", outbox_status, nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("correlation_id", sa.String(64), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_notification_outbox"),
        sa.ForeignKeyConstraint(
            ["reservation_id"], ["reservations.id"],
            name="fk_notification_outbox_reservation_id_reservations", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["laundromat_id"], ["laundromats.id"],
            name="fk_notification_outbox_laundromat_id_laundromats", ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_notification_outbox_reservation_id", "notification_outbox", ["reservation_id"])
    op.create_index("ix_notification_outbox_laundromat_id", "notification_outbox", ["laundromat_id"])
    op.create_index(
        "ix_notification_outbox_status_next_attempt_at", "notification_outbox", ["status", "next_attempt_at"]
    )


def downgrade() -> None:
    op.drop_table("notification_outbox")
    outbox_status.drop(op.get_bind(), checkfirst=True)
