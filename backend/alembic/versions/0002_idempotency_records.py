"""idempotency_records: the stored outcome of each Idempotency-Key attempt (US-5.2).

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-22
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "idempotency_records",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("endpoint", sa.String(100), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("error_code", sa.String(50), nullable=True),
        sa.Column("response_body", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        # One record per (caller, key): the INSERT ... ON CONFLICT DO NOTHING of a twin request finds it.
        sa.PrimaryKeyConstraint("user_id", "key", name="pk_idempotency_records"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_idempotency_records_user_id_users", ondelete="CASCADE"
        ),
    )
    op.create_index("ix_idempotency_records_created_at", "idempotency_records", ["created_at"])


def downgrade() -> None:
    op.drop_table("idempotency_records")
