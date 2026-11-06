"""Alembic environment.

URL: DATABASE_URL by default. `alembic -x db=test upgrade head` targets TEST_DATABASE_URL instead.
Tests pass an open connection through config.attributes["connection"].
"""
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app.core.config import get_settings, to_sqlalchemy_url
from app.data.tables import Base

config = context.config
if config.config_file_name and not config.attributes.get("connection"):
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def database_url() -> str:
    settings = get_settings()
    use_test = context.get_x_argument(as_dictionary=True).get("db") == "test"
    url = settings.test_database_url if use_test else settings.database_url
    if not url:
        name = "TEST_DATABASE_URL" if use_test else "DATABASE_URL"
        raise RuntimeError(f"{name} is not set. Copy backend/.env.example to backend/.env.")
    return to_sqlalchemy_url(url)


def run_offline() -> None:
    """`alembic upgrade head --sql`: print the SQL without connecting."""
    context.configure(
        url=database_url() if get_settings().database_url else "postgresql+psycopg://offline/washslot",
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_with(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def run_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        run_with(connection)
        return
    engine = create_engine(database_url(), poolclass=pool.NullPool)
    with engine.connect() as conn:
        run_with(conn)


if context.is_offline_mode():
    run_offline()
else:
    run_online()
