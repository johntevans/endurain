"""Create homelab.sleep_heart_rate

Homelab fork revision: only ever touches the `homelab` schema.

Nightly sleeping heart rate from Eight Sleep with its 7-day average, the
user's baseline and usual range, the same shape as homelab.sleep_hrv. The
night's value is also in upstream's health_sleep.resting_heart_rate; this adds
what upstream has no column for. Rebuilt by the Eight Sleep sync's history
run, so dropping it loses nothing that cannot be fetched again.

Revision ID: hl0006
Revises: hl0005
Create Date: 2026-10-22 00:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "hl0006"
down_revision: str | None = "hl0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sleep_heart_rate",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("hr_bpm", sa.Float(), nullable=False),
        sa.Column("avg_7d_bpm", sa.Float(), nullable=True),
        sa.Column("baseline_bpm", sa.Float(), nullable=True),
        sa.Column("range_low_bpm", sa.Float(), nullable=True),
        sa.Column("range_high_bpm", sa.Float(), nullable=True),
        sa.Column("source", sa.String(length=16), nullable=False),
        # Unqualified on purpose, as in hl0001: resolves through search_path to
        # upstream's tables.
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="sleep_heart_rate_user_id_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "date", name="sleep_heart_rate_pkey"),
        sa.CheckConstraint("hr_bpm > 0", name="sleep_heart_rate_hr_bpm_check"),
        schema="homelab",
    )


def downgrade() -> None:
    op.drop_table("sleep_heart_rate", schema="homelab")
