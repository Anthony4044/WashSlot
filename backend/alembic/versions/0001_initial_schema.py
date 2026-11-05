"""Initial schema: every table Milestone 1 needs.

users, laundromats, machines, machine_slots, reservations.
Later: 0002 idempotency_records (US-5.2), 0003 notification_outbox (US-6.1).

Revision ID: 0001
Revises:
Create Date: 2026-11-04
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

user_role = sa.Enum("CUSTOMER", "OPERATOR", name="user_role")
machine_type = sa.Enum("WASHER", "DRYER", name="machine_type")
reservation_status = sa.Enum("HELD", "CONFIRMED", "EXPIRED", "CANCELLED", "NO_SHOW", name="reservation_status")


def created_at() -> sa.Column:
    return sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", user_role, server_default="CUSTOMER", nullable=False),
        created_at(),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )

    op.create_table(
        "laundromats",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("address", sa.String(255), nullable=False),
        sa.Column("operator_id", sa.BigInteger(), nullable=True),
        sa.Column("timezone", sa.String(64), server_default="America/Toronto", nullable=False),
        created_at(),
        sa.PrimaryKeyConstraint("id", name="pk_laundromats"),
        sa.ForeignKeyConstraint(
            ["operator_id"], ["users.id"], name="fk_laundromats_operator_id_users", ondelete="SET NULL"
        ),
    )
    op.create_index("ix_laundromats_operator_id", "laundromats", ["operator_id"])

    op.create_table(
        "machines",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("laundromat_id", sa.BigInteger(), nullable=False),
        sa.Column("label", sa.String(50), nullable=False),
        sa.Column("type", machine_type, nullable=False),
        sa.Column("reservable", sa.Boolean(), server_default=sa.false(), nullable=False),
        created_at(),
        sa.PrimaryKeyConstraint("id", name="pk_machines"),
        sa.ForeignKeyConstraint(
            ["laundromat_id"], ["laundromats.id"], name="fk_machines_laundromat_id_laundromats", ondelete="CASCADE"
        ),
        sa.UniqueConstraint("laundromat_id", "label", name="uq_machines_laundromat_label"),
    )
    op.create_index("ix_machines_laundromat_id", "machines", ["laundromat_id"])

    op.create_table(
        "machine_slots",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("machine_id", sa.BigInteger(), nullable=False),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=False),
        created_at(),
        sa.PrimaryKeyConstraint("id", name="pk_machine_slots"),
        sa.ForeignKeyConstraint(
            ["machine_id"], ["machines.id"], name="fk_machine_slots_machine_id_machines", ondelete="CASCADE"
        ),
        sa.UniqueConstraint("machine_id", "start_time", name="uq_machine_slots_machine_start"),
        # Short names: the naming convention adds the "ck_<table>_" prefix (same as the models).
        sa.CheckConstraint("end_time > start_time", name="end_after_start"),
    )
    op.create_index("ix_machine_slots_start_time", "machine_slots", ["start_time"])

    op.create_table(
        "reservations",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("slot_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("status", reservation_status, nullable=False),
        sa.Column("confirmation_email", sa.String(320), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("checked_in_at", sa.DateTime(timezone=True), nullable=True),
        created_at(),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_reservations"),
        sa.ForeignKeyConstraint(
            ["slot_id"], ["machine_slots.id"], name="fk_reservations_slot_id_machine_slots", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_reservations_user_id_users", ondelete="RESTRICT"
        ),
        sa.CheckConstraint("status <> 'HELD' OR expires_at IS NOT NULL", name="held_has_expiry"),
    )
    op.create_index("ix_reservations_slot_id", "reservations", ["slot_id"])
    op.create_index("ix_reservations_user_id", "reservations", ["user_id"])
    op.create_index("ix_reservations_status_expires_at", "reservations", ["status", "expires_at"])
    # Safety net behind the row lock: at most one HELD/CONFIRMED reservation per slot.
    op.create_index(
        "uq_reservations_active_slot",
        "reservations",
        ["slot_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('HELD', 'CONFIRMED')"),
    )


def downgrade() -> None:
    op.drop_table("reservations")
    op.drop_table("machine_slots")
    op.drop_table("machines")
    op.drop_table("laundromats")
    op.drop_table("users")
    reservation_status.drop(op.get_bind(), checkfirst=True)
    machine_type.drop(op.get_bind(), checkfirst=True)
    user_role.drop(op.get_bind(), checkfirst=True)
