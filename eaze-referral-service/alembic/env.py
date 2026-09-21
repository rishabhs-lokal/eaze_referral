import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.config import get_settings
from app.db import to_asyncpg_url
from app.models import Base

# Alembic Config object, giving access to alembic.ini values.
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Autogenerate diffs against this metadata — the SQLAlchemy models in app/models.py are the
# single source of truth for the schema.
target_metadata = Base.metadata

# The one place the connection string is read from: the same Settings the app itself uses, so
# `DATABASE_URL` (or a `.env` file) controls migrations identically to the running service.
config.set_main_option("sqlalchemy.url", to_asyncpg_url(get_settings().database_url))


def run_migrations_offline() -> None:
    """`alembic upgrade head --sql` — emits SQL without a live DB connection."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Alembic's official pattern for async SQLAlchemy projects (`alembic init -t async`):
    build an AsyncEngine, then run the actual migration functions via `run_sync`, since Alembic's
    migration execution itself is synchronous."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
