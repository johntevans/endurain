"""Allow the Daniels 2Q tag in homelab.activity_tags

Homelab fork revision: only ever touches the `homelab` schema.

Widens the tag CHECK constraint with daniels_2q. Downgrading first deletes
any rows carrying that tag, since the narrower constraint cannot be restored
while they exist.

Revision ID: hl0008
Revises: hl0007
Create Date: 2026-11-09 00:00:00

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "hl0008"
down_revision: str | None = "hl0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONSTRAINT = "activity_tags_tag_check"
OLD_TAGS = "'race', 'workout', 'long_run', 'nsm_short', 'nsm_medium', 'nsm_long'"
NEW_TAGS = "'race', 'workout', 'long_run', 'nsm_short', 'nsm_medium', 'nsm_long', 'daniels_2q'"


def upgrade() -> None:
    op.drop_constraint(CONSTRAINT, "activity_tags", schema="homelab", type_="check")
    op.create_check_constraint(CONSTRAINT, "activity_tags", f"tag IN ({NEW_TAGS})", schema="homelab")


def downgrade() -> None:
    op.execute("DELETE FROM homelab.activity_tags WHERE tag = 'daniels_2q'")
    op.drop_constraint(CONSTRAINT, "activity_tags", schema="homelab", type_="check")
    op.create_check_constraint(CONSTRAINT, "activity_tags", f"tag IN ({OLD_TAGS})", schema="homelab")
