"""Run the fork's Alembic environment (``homelab/alembic``).

Called from ``main.py`` right after upstream's ``_run_alembic_migrations``,
so upstream's tables (which fork tables reference) always exist first.
"""

from pathlib import Path

from alembic.config import Config

from alembic import command
from homelab.database import SCHEMA

ALEMBIC_DIR = Path(__file__).resolve().parent / "alembic"

# Alembic's version table for this environment, kept inside the schema so the
# fork's state lives (and can be dropped) entirely within ``homelab``.
VERSION_TABLE = "alembic_version"


def include_name(name: str | None, type_: str, parent_names: dict) -> bool:
    """Limit autogenerate to the ``homelab`` schema.

    Without this, autogenerate would compare the fork metadata against the
    default (``public``) schema and propose dropping every upstream table.
    """
    if type_ == "schema":
        return name == SCHEMA
    return True


def include_object(obj, name: str | None, type_: str, reflected: bool, compare_to) -> bool:
    """Leave foreign keys into upstream's schema out of autogenerate.

    Fork models cannot declare them (see ``homelab.database``), so they are
    written by hand in the migrations; without this, autogenerate would
    propose dropping them.
    """
    if type_ == "foreign_key_constraint":
        return obj.referred_table.schema == SCHEMA
    return True


def build_config() -> Config:
    """Build an Alembic config for the fork environment.

    Uses an absolute ``script_location`` so it works regardless of the
    process working directory, and needs no ``.ini`` file at runtime.

    Returns:
        The Alembic ``Config`` for ``homelab/alembic``.
    """
    config = Config()
    config.set_main_option("script_location", str(ALEMBIC_DIR))
    # Same as upstream: leave logging configuration to the app.
    config.attributes["configure_logger"] = False
    return config


def run_homelab_migrations() -> None:
    """Upgrade the ``homelab`` schema to head.

    Critical, like upstream's: a failure aborts startup because the fork
    endpoints cannot work against a schema in an unknown state.
    """
    command.upgrade(build_config(), "head")
