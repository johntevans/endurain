"""Declarative base for fork-owned tables in the ``homelab`` schema.

Fork models use their own ``DeclarativeBase`` and ``MetaData`` instead of
upstream's ``core.database.Base`` so that:

- upstream's Alembic autogenerate never sees them (it would otherwise emit
  ``create_table`` for fork tables into upstream's revision chain), and
- upstream's ``Base.metadata.create_all`` (used by the SQLite test helper)
  does not try to create tables in a schema SQLite does not have.

Cross-schema foreign keys to upstream tables (``activities.id``) are declared
in the migrations only; the ORM models here are plain columns, because a
``ForeignKey`` can only resolve against a table in the same ``MetaData``.
"""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

SCHEMA = "homelab"


class HomelabBase(DeclarativeBase):
    """Base class for every fork-owned ORM model."""

    metadata = MetaData(schema=SCHEMA)
