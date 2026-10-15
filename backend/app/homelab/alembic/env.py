"""Alembic environment for the homelab fork's own schema.

This is the SECOND Alembic environment in the backend. Upstream's lives in
``app/alembic`` and owns the ``public`` schema; this one owns only the
``homelab`` schema and keeps its version table there
(``homelab.alembic_version``), so the two never see each other's revisions.
Dropping the ``homelab`` schema returns the database to vanilla Endurain.
"""

import pathlib
from importlib import import_module
from logging.config import fileConfig

from sqlalchemy import text

from alembic import context
from homelab.database import SCHEMA, HomelabBase
from homelab.db_migrations import VERSION_TABLE, include_name, include_object

config = context.config

if config.attributes.get("configure_logger", True) and config.config_file_name:
    fileConfig(config.config_file_name)


def _import_homelab_models() -> None:
    """Import every ``homelab/**/models.py`` so the metadata is complete."""
    homelab_dir = pathlib.Path(__file__).resolve().parents[1]
    app_dir = homelab_dir.parent
    for path in sorted(homelab_dir.glob("**/models.py")):
        import_module(".".join(path.relative_to(app_dir).with_suffix("").parts))


_import_homelab_models()
target_metadata = HomelabBase.metadata


_CONFIGURE_KWARGS = {
    "target_metadata": target_metadata,
    "version_table": VERSION_TABLE,
    "version_table_schema": SCHEMA,
    "include_schemas": True,
    "include_name": include_name,
    "include_object": include_object,
}


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of running against a database."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        **_CONFIGURE_KWARGS,
    )
    with context.begin_transaction():
        # The version table lives in the schema, so it must exist first.
        context.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations with the application's engine."""
    from core.database import engine

    with engine.connect() as connection:
        # The version table lives in the schema, so create it before Alembic
        # looks for the version table. Checking first avoids needing CREATE
        # privilege on the database once the schema exists.
        exists = connection.execute(
            text("SELECT 1 FROM pg_namespace WHERE nspname = :name"),
            {"name": SCHEMA},
        ).scalar()
        if not exists:
            connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}"))
        connection.commit()

        context.configure(connection=connection, **_CONFIGURE_KWARGS)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
