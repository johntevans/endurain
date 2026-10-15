"""Homelab fork: sanity checks for the second Alembic environment.

The suite has no Postgres, so these check the revision graph and the SQL the
environment emits in offline mode, which is what runs at startup.
"""

import io
from pathlib import Path
from unittest.mock import patch

from alembic.config import Config
from alembic.script import ScriptDirectory

from alembic import command
from homelab import db_migrations
from homelab.database import SCHEMA, HomelabBase

APP_DIR = Path(db_migrations.__file__).resolve().parents[1]


def _offline_sql() -> str:
    config = db_migrations.build_config()
    config.set_main_option("sqlalchemy.url", "postgresql+psycopg://")
    config.output_buffer = io.StringIO()
    command.upgrade(config, "head", sql=True)
    return config.output_buffer.getvalue()


def test_config_points_at_the_fork_environment():
    config = db_migrations.build_config()
    location = Path(config.get_main_option("script_location"))
    assert location.is_absolute()
    assert location == APP_DIR / "homelab" / "alembic"
    assert config.attributes["configure_logger"] is False


def test_single_linear_chain_separate_from_upstream():
    fork = ScriptDirectory.from_config(db_migrations.build_config())
    assert fork.get_heads() == ["hl0001"]
    assert fork.get_base() == "hl0001"

    upstream_config = Config()
    upstream_config.set_main_option("script_location", str(APP_DIR / "alembic"))
    upstream_ids = {rev.revision for rev in ScriptDirectory.from_config(upstream_config).walk_revisions()}
    fork_ids = {rev.revision for rev in fork.walk_revisions()}
    assert upstream_ids
    assert not fork_ids & upstream_ids
    assert all(rev_id.startswith("hl") for rev_id in fork_ids)


def test_upgrade_creates_the_schema_first_and_keeps_its_version_table_there():
    sql = _offline_sql()

    schema_at = sql.index(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
    assert schema_at < sql.index(f"CREATE TABLE {SCHEMA}.alembic_version")
    assert f"CREATE TABLE {SCHEMA}.activity_tags" in sql
    assert "REFERENCES activities (id) ON DELETE CASCADE" in sql
    assert "CHECK (tag IN ('race', 'workout', 'long_run'))" in sql
    assert f"INSERT INTO {SCHEMA}.alembic_version" in sql
    # Never touches upstream's version table or tables.
    assert "public." not in sql
    assert "INSERT INTO alembic_version" not in sql


def test_fork_models_stay_out_of_upstream_metadata():
    from core.database import Base

    assert all(table.schema == SCHEMA for table in HomelabBase.metadata.tables.values())
    assert not any(table.schema == SCHEMA for table in Base.metadata.tables.values())
    assert "homelab.activity_tags" in HomelabBase.metadata.tables


def test_run_homelab_migrations_upgrades_to_head():
    with patch.object(db_migrations.command, "upgrade") as upgrade:
        db_migrations.run_homelab_migrations()
    config, target = upgrade.call_args.args
    assert target == "head"
    assert config.get_main_option("script_location").endswith("homelab/alembic")


def test_autogenerate_is_limited_to_the_homelab_schema():
    from types import SimpleNamespace

    assert db_migrations.include_name(SCHEMA, "schema", {}) is True
    assert db_migrations.include_name(None, "schema", {}) is False
    assert db_migrations.include_name("public", "schema", {}) is False
    assert db_migrations.include_name("activity_tags", "table", {}) is True

    def fk(schema):
        return SimpleNamespace(referred_table=SimpleNamespace(schema=schema))

    assert db_migrations.include_object(fk(None), "fk", "foreign_key_constraint", True, None) is False
    assert db_migrations.include_object(fk(SCHEMA), "fk", "foreign_key_constraint", True, None) is True
    assert db_migrations.include_object(None, "activity_tags", "table", True, None) is True
