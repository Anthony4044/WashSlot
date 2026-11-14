"""Seed 2 laundromats, ~8 machines each (some walk-in only), and 1-hour slots for the next 7 days.

From backend/:   python scripts/seed_laundromats.py          (DATABASE_URL)
                 python scripts/seed_laundromats.py --test   (TEST_DATABASE_URL)

Safe to run again: existing laundromats (matched by name) keep their machines; missing slots
for the next 7 days are added. Links operator_id to operator@example.com when that user exists
(run seed_users.py first).
"""
from __future__ import annotations

import argparse
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.data.database import make_engine, make_session_factory  # noqa: E402
from app.data.tables import LaundromatRow, MachineRow, MachineSlotRow, UserRow  # noqa: E402
from app.domain.enums import MachineType  # noqa: E402

TIMEZONE = "America/Toronto"
SLOT_HOURS = range(8, 20)  # 08:00–19:00 local starts → 12 one-hour slots/day
DAYS_AHEAD = 7

# (name, address, machines: list of (label, type, reservable))
SEED_LAUNDROMATS: list[tuple[str, str, list[tuple[str, MachineType, bool]]]] = [
    (
        "Spin City",
        "1450 Sainte-Catherine St W, Montreal",
        [
            ("Washer 1", MachineType.WASHER, True),
            ("Washer 2", MachineType.WASHER, True),
            ("Washer 3", MachineType.WASHER, True),
            ("Washer 4", MachineType.WASHER, True),
            ("Washer 5", MachineType.WASHER, False),  # walk-in only
            ("Dryer 1", MachineType.DRYER, True),
            ("Dryer 2", MachineType.DRYER, True),
            ("Dryer 3", MachineType.DRYER, False),  # walk-in only
        ],
    ),
    (
        "Fresh Cycle",
        "2150 Rue Guy, Montreal",
        [
            ("Washer 1", MachineType.WASHER, True),
            ("Washer 2", MachineType.WASHER, True),
            ("Washer 3", MachineType.WASHER, True),
            ("Washer 4", MachineType.WASHER, False),
            ("Dryer 1", MachineType.DRYER, True),
            ("Dryer 2", MachineType.DRYER, True),
            ("Dryer 3", MachineType.DRYER, True),
            ("Dryer 4", MachineType.DRYER, False),
        ],
    ),
]


def _operator_id(session: Session) -> int | None:
    row = session.scalar(select(UserRow).where(UserRow.email == "operator@example.com"))
    return row.id if row else None


def _ensure_laundromat(
    session: Session, name: str, address: str, operator_id: int | None
) -> tuple[LaundromatRow, bool]:
    existing = session.scalar(select(LaundromatRow).where(LaundromatRow.name == name))
    if existing is not None:
        if operator_id is not None and existing.operator_id is None:
            existing.operator_id = operator_id
        return existing, False
    row = LaundromatRow(name=name, address=address, operator_id=operator_id, timezone=TIMEZONE)
    session.add(row)
    session.flush()
    return row, True


def _ensure_machine(
    session: Session, laundromat_id: int, label: str, machine_type: MachineType, reservable: bool
) -> tuple[MachineRow, bool]:
    existing = session.scalar(
        select(MachineRow).where(MachineRow.laundromat_id == laundromat_id, MachineRow.label == label)
    )
    if existing is not None:
        existing.reservable = reservable
        existing.type = machine_type
        return existing, False
    row = MachineRow(laundromat_id=laundromat_id, label=label, type=machine_type, reservable=reservable)
    session.add(row)
    session.flush()
    return row, True


def _slot_starts(today_local: date, tz: ZoneInfo) -> list[datetime]:
    starts: list[datetime] = []
    for day_offset in range(DAYS_AHEAD):
        day = today_local + timedelta(days=day_offset)
        for hour in SLOT_HOURS:
            starts.append(datetime(day.year, day.month, day.day, hour, 0, tzinfo=tz))
    return starts


def _ensure_slots(session: Session, machine_id: int, starts: list[datetime]) -> int:
    """Add missing 1-hour slots. Returns how many were created."""
    existing = {
        row.start_time.astimezone(UTC)
        for row in session.scalars(select(MachineSlotRow).where(MachineSlotRow.machine_id == machine_id)).all()
    }
    created = 0
    for start in starts:
        if start.astimezone(UTC) in existing:
            continue
        session.add(MachineSlotRow(machine_id=machine_id, start_time=start, end_time=start + timedelta(hours=1)))
        created += 1
    if created:
        session.flush()
    return created


def seed(session: Session) -> list[str]:
    tz = ZoneInfo(TIMEZONE)
    today_local = datetime.now(tz).date()
    starts = _slot_starts(today_local, tz)
    operator_id = _operator_id(session)
    lines: list[str] = []

    for name, address, machines in SEED_LAUNDROMATS:
        laundromat, lm_created = _ensure_laundromat(session, name, address, operator_id)
        lines.append(f"{'created' if lm_created else 'exists '}  laundromat {name}")
        for label, machine_type, reservable in machines:
            machine, mch_created = _ensure_machine(session, laundromat.id, label, machine_type, reservable)
            slots_created = _ensure_slots(session, machine.id, starts)
            flag = "created" if mch_created else "exists "
            lines.append(
                f"  {flag}  {label} (reservable={reservable})  +{slots_created} slots"
            )
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--test", action="store_true", help="seed TEST_DATABASE_URL instead of DATABASE_URL")
    args = parser.parse_args()

    settings = get_settings()
    url = settings.test_database_url if args.test else settings.database_url
    if not url:
        print(f"{'TEST_DATABASE_URL' if args.test else 'DATABASE_URL'} is not set (see backend/.env.example).")
        return 1

    engine = make_engine(url)
    session_factory = make_session_factory(engine)
    try:
        with session_factory() as session:
            with session.begin():
                for line in seed(session):
                    print(line)
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
