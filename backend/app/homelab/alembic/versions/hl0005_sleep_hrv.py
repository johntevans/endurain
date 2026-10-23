"""Create homelab.sleep_hrv

Homelab fork revision: only ever touches the `homelab` schema.

Nightly HRV from Eight Sleep (the night's value, its 7-day average, the
user's baseline and usual range), keyed like upstream's health_sleep by user
and wake-up date. Rebuilt by the Eight Sleep sync's daily history run, so
dropping it loses nothing that cannot be fetched again.

Revision ID: hl0005
Revises: hl0004
Create Date: 2026-10-22 00:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "hl0005"
down_revision: str | None = "hl0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sleep_hrv",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("hrv_ms", sa.Float(), nullable=False),
        sa.Column("avg_7d_ms", sa.Float(), nullable=True),
        sa.Column("baseline_ms", sa.Float(), nullable=True),
        sa.Column("range_low_ms", sa.Float(), nullable=True),
        sa.Column("range_high_ms", sa.Float(), nullable=True),
        sa.Column("source", sa.String(length=16), nullable=False),
        # Unqualified on purpose, as in hl0001: resolves through search_path to
        # upstream's tables.
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="sleep_hrv_user_id_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "date", name="sleep_hrv_pkey"),
        sa.CheckConstraint("hrv_ms > 0", name="sleep_hrv_hrv_ms_check"),
        schema="homelab",
    )


def downgrade() -> None:
    op.drop_table("sleep_hrv", schema="homelab")
