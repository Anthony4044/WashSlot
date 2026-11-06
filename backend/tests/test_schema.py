"""Migration 001 against a real Postgres (your Neon test database). Skipped without TEST_DATABASE_URL."""
from datetime import timedelta

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from app.data.tables import Base, MachineSlotRow, ReservationRow, UserRow
from app.domain.enums import ReservationStatus
from tests.factories import START, make_reservation, make_slot, make_user


def test_migration_creates_all_milestone_1_tables(db_engine):
    tables = set(inspect(db_engine).get_table_names())
    assert {"users", "laundromats", "machines", "machine_slots", "reservations"} <= tables


def test_migration_matches_the_tables(db_engine):
    """If someone changes a table class without a migration (or the reverse), this fails."""
    with db_engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True}), Base.metadata)
    assert diff == []


def test_only_one_active_reservation_per_slot(db_session):
    user, slot = make_user(db_session), make_slot(db_session)
    make_reservation(db_session, user, slot)
    with pytest.raises(IntegrityError):
        make_reservation(db_session, user, slot, ReservationStatus.CONFIRMED)


def test_slot_can_be_held_again_after_expiry(db_session):
    user, slot = make_user(db_session), make_slot(db_session)
    make_reservation(db_session, user, slot, ReservationStatus.EXPIRED)
    make_reservation(db_session, user, slot, ReservationStatus.CANCELLED)
    make_reservation(db_session, user, slot)  # no error: expired/cancelled rows don't block the slot
    db_session.commit()


def test_held_reservation_needs_an_expiry(db_session):
    user, slot = make_user(db_session), make_slot(db_session)
    db_session.add(ReservationRow(slot_id=slot.id, user_id=user.id, status=ReservationStatus.HELD,
                                  confirmation_email=user.email, expires_at=None))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_slot_must_end_after_it_starts(db_session):
    slot = make_slot(db_session)
    db_session.add(MachineSlotRow(machine_id=slot.machine_id, start_time=START + timedelta(hours=2), end_time=START))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_emails_are_unique(db_session):
    make_user(db_session)
    db_session.add(UserRow(email="a@example.com", password_hash="y"))
    with pytest.raises(IntegrityError):
        db_session.flush()
