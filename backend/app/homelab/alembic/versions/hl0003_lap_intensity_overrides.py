"""Create homelab.lap_intensity_overrides

Homelab fork revision: only ever touches the `homelab` schema.

The owner's corrections of lap intensity, one row per corrected lap. The
recorded value in upstream's activity_laps.intensity is never changed; laps
with neither a recorded value nor an override read as the default in code.

Revision ID: hl0003
Revises: hl0002
Create Date: 2026-10-15 00:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "hl0003"
down_revision: str | None = "hl0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INTENSITIES = "'active', 'interval', 'warmup', 'cooldown', 'recovery', 'rest', 'other'"


def upgrade() -> None:
    op.create_table(
        "lap_intensity_overrides",
        sa.Column("lap_id", sa.Integer(), nullable=False),
        sa.Column("intensity", sa.String(length=16), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        # Unqualified on purpose, as in hl0001: resolves through search_path to
        # upstream's tables.
        sa.ForeignKeyConstraint(
            ["lap_id"],
            ["activity_laps.id"],
            name="lap_intensity_overrides_lap_id_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("lap_id", name="lap_intensity_overrides_pkey"),
        sa.CheckConstraint(
            f"intensity IN ({INTENSITIES})",
            name="lap_intensity_overrides_intensity_check",
        ),
        schema="homelab",
    )


def downgrade() -> None:
    op.drop_table("lap_intensity_overrides", schema="homelab")
