"""Create homelab.training_load_settings and homelab.activity_loads

Homelab fork revision: only ever touches the `homelab` schema.

The owner's Intervals.icu thresholds, and a cache of each activity's
Intervals-style training load computed from them. Both are rebuilt from
upstream's data plus the settings; dropping them loses nothing else.

Revision ID: hl0004
Revises: hl0003
Create Date: 2026-10-22 00:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "hl0004"
down_revision: str | None = "hl0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "training_load_settings",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("resting_hr", sa.Integer(), nullable=False),
        sa.Column("threshold_hr", sa.Integer(), nullable=False),
        sa.Column("max_hr", sa.Integer(), nullable=False),
        sa.Column("threshold_pace", sa.Float(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        # Unqualified on purpose, as in hl0001: resolves through search_path to
        # upstream's tables.
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="training_load_settings_user_id_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", name="training_load_settings_pkey"),
        sa.CheckConstraint(
            "resting_hr > 0 AND threshold_hr > resting_hr AND max_hr >= threshold_hr AND threshold_pace > 0",
            name="training_load_settings_range_check",
        ),
        schema="homelab",
    )
    op.create_table(
        "activity_loads",
        sa.Column("activity_id", sa.Integer(), nullable=False),
        sa.Column("load", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=8), nullable=False),
        sa.Column("pace_load", sa.Float(), nullable=True),
        sa.Column("hr_load", sa.Float(), nullable=True),
        sa.Column("activity_type", sa.Integer(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["activity_id"],
            ["activities.id"],
            name="activity_loads_activity_id_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("activity_id", name="activity_loads_pkey"),
        sa.CheckConstraint("source IN ('pace', 'hr', 'none')", name="activity_loads_source_check"),
        schema="homelab",
    )


def downgrade() -> None:
    op.drop_table("activity_loads", schema="homelab")
    op.drop_table("training_load_settings", schema="homelab")
