from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect, text

from app import migrate
from app.models import Base
from app.migrate import compare_type


def diffs(conn):
    ctx = MigrationContext.configure(conn, opts={"compare_type": compare_type})
    return compare_metadata(ctx, Base.metadata)


async def test_migrations_build_exactly_the_models(app):
    async with app.state.engine.connect() as conn:
        assert await conn.run_sync(diffs) == []
        assert (await conn.execute(text("SELECT version_num FROM alembic_version"))).scalar() == "0002"


async def test_database_from_before_migrations_is_upgraded_in_place(app):
    """A database create_all made (no alembic_version table) keeps its data and gets the new tables."""
    from alembic import command

    async with app.state.engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.execute(text("DROP TABLE alembic_version"))
        await conn.run_sync(lambda c: command.upgrade(migrate._config(c), "0001"))  # the old schema
        await conn.execute(text("DROP TABLE alembic_version"))
        await conn.execute(text("INSERT INTO users (id, address, created_at, last_login_at, last_seen_at) "
                                "VALUES (1, '0xabc', '2026-01-01', '2026-01-01', '2026-01-01')"))
        await conn.execute(text(
            "INSERT INTO paper_trades (id, user_id, from_asset, to_asset, amount_in, amount_out, price_in_usd, "
            "price_out_usd, fee_usd, created_at, archived) VALUES (1, 1, 'USDC', 'ETH', 1, 1, 1, 1, 0, '2026-01-01', false)"))
    await app.state.init_db()
    async with app.state.engine.connect() as conn:
        assert await conn.run_sync(diffs) == []
        assert (await conn.execute(text("SELECT source FROM paper_trades"))).scalar() == "manual"
        assert "paper_bots" in await conn.run_sync(lambda c: inspect(c).get_table_names())
    await app.state.init_db()  # running again is a no-op
