"""Database migrations (Alembic), applied by the API on start-up."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Numeric, inspect

from .models import Amount

MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"
BASELINE = "0001"  # the schema create_all made before migrations existed


def compare_type(ctx, inspected_column, metadata_column, inspected_type, metadata_type):
    """Amount is NUMERIC on PostgreSQL and text on SQLite by design; compare what it becomes on this database."""
    if isinstance(metadata_type, Amount):
        impl = metadata_type.load_dialect_impl(ctx.dialect)
        if impl._type_affinity is not inspected_type._type_affinity:  # e.g. NUMERIC vs text
            return True
        if isinstance(impl, Numeric):
            return (impl.precision, impl.scale) != (inspected_type.precision, inspected_type.scale)
        return impl.length != inspected_type.length
    return None  # Alembic's default comparison


def _config(connection) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS))
    cfg.attributes["connection"] = connection
    return cfg


def upgrade(connection) -> None:
    """Bring the database to the latest schema. Run with a sync connection (AsyncConnection.run_sync)."""
    cfg = _config(connection)
    tables = set(inspect(connection).get_table_names())
    if "users" in tables and "alembic_version" not in tables:
        command.stamp(cfg, BASELINE)  # an older database: record that it already has the first schema
    command.upgrade(cfg, "head")
