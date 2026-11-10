"""Create the demo accounts: 2 customers and 1 operator. Safe to run again (existing emails are skipped).

From backend/:   python scripts/seed_users.py          (DATABASE_URL, the shared demo database)
                 python scripts/seed_users.py --test   (TEST_DATABASE_URL, your own test database)

This is the ONLY way to create an OPERATOR: POST /auth/register always makes a customer.
The passwords below are for the demo only; they are printed in the README on purpose.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # lets "python scripts/..." import app

from app.core.config import get_settings  # noqa: E402
from app.core.passwords import PasswordHasher  # noqa: E402
from app.data.database import make_engine, make_session_factory  # noqa: E402
from app.data.unit_of_work import SqlAlchemyUnitOfWork  # noqa: E402
from app.domain.enums import UserRole  # noqa: E402
from app.domain.user import User, normalize_email  # noqa: E402

SEED_USERS = [
    ("alice@example.com", "customer123", UserRole.CUSTOMER),
    ("bob@example.com", "customer123", UserRole.CUSTOMER),
    ("operator@example.com", "operator123", UserRole.OPERATOR),
]


def seed(uow_factory, hasher: PasswordHasher) -> list[tuple[str, bool]]:
    """Returns (email, created?) for each seed user. One unit of work: all or nothing."""
    results = []
    with uow_factory() as uow:
        for email, password, role in SEED_USERS:
            user = User(id=None, email=normalize_email(email), password_hash=hasher.hash(password), role=role)
            results.append((user.email, uow.users.add(user) is not None))
    return results


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
        results = seed(lambda: SqlAlchemyUnitOfWork(session_factory), PasswordHasher())
    finally:
        engine.dispose()
    for email, created in results:
        print(f"{'created' if created else 'exists '}  {email}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
