"""Create the homelab schema and homelab.activity_tags

Homelab fork revision: only ever touches the `homelab` schema.

The first fork revision. It creates the schema itself so it also works on a
copy of a production database that has never seen the fork (env.py creates
the schema too, because Alembic's version table lives in it).

Revision ID: hl0001
Revises:
Create Date: 2026-10-15 00:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "hl0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS homelab")
    op.create_table(
        "activity_tags",
        sa.Column("activity_id", sa.Integer(), nullable=False),
        sa.Column("tag", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        # Unqualified on purpose: resolves through search_path to wherever
        # upstream's tables live (public), the same way upstream's own do.
        sa.ForeignKeyConstraint(
            ["activity_id"],
            ["activities.id"],
            name="activity_tags_activity_id_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("activity_id", "tag", name="activity_tags_pkey"),
        sa.CheckConstraint(
            "tag IN ('race', 'workout', 'long_run')",
            name="activity_tags_tag_check",
        ),
        schema="homelab",
    )
    # The list filter looks activities up by tag.
    op.create_index(
        "ix_activity_tags_tag_activity_id",
        "activity_tags",
        ["tag", "activity_id"],
        schema="homelab",
    )


def downgrade() -> None:
    # The schema itself stays: it holds this environment's version table.
    op.drop_index("ix_activity_tags_tag_activity_id", table_name="activity_tags", schema="homelab")
    op.drop_table("activity_tags", schema="homelab")
