"""Create homelab.withings_tokens

Homelab fork revision: only ever touches the `homelab` schema.

One row per user who has linked Withings: the Withings user id and the OAuth
tokens, both Fernet-encrypted with FERNET_KEY. Each refresh replaces the
refresh token, which is why it is stored here and not in .env. Dropping the
table only unlinks Withings (link again with `python -m homelab.withings.cli
link`).

Revision ID: hl0007
Revises: hl0006
Create Date: 2026-10-22 00:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "hl0007"
down_revision: str | None = "hl0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "withings_tokens",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("withings_userid", sa.String(length=32), nullable=False),
        sa.Column("access_token", sa.Text(), nullable=False),
        sa.Column("refresh_token", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scope", sa.String(length=128), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        # Unqualified on purpose, as in hl0001: resolves through search_path to
        # upstream's tables.
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="withings_tokens_user_id_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", name="withings_tokens_pkey"),
        schema="homelab",
    )


def downgrade() -> None:
    op.drop_table("withings_tokens", schema="homelab")
