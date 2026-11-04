"""Alembic environment. The API runs migrations through app.migrate, passing its own connection in;
the `alembic` command line connects using the API's settings."""

import asyncio

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import Settings
from app.migrate import compare_type
from app.models import Base

target_metadata = Base.metadata


def run(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=compare_type,
                      render_as_batch=connection.dialect.name == "sqlite")  # SQLite can't alter columns in place
    with context.begin_transaction():
        context.run_migrations()


async def run_cli() -> None:
    engine = create_async_engine(Settings().database_url)
    async with engine.connect() as conn:
        await conn.run_sync(run)
        await conn.commit()
    await engine.dispose()


connection = context.config.attributes.get("connection")
if connection is not None:
    run(connection)
else:
    asyncio.run(run_cli())
