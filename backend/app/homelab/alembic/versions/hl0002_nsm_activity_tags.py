"""Allow the Norwegian Singles Method tags in homelab.activity_tags

Homelab fork revision: only ever touches the `homelab` schema.

Widens the tag CHECK constraint with nsm_short, nsm_medium and nsm_long.
Downgrading first deletes any rows carrying those tags, since the narrower
constraint cannot be restored while they exist.

Revision ID: hl0002
Revises: hl0001
Create Date: 2026-10-15 00:00:00

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "hl0002"
down_revision: str | None = "hl0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONSTRAINT = "activity_tags_tag_check"
OLD_TAGS = "'race', 'workout', 'long_run'"
NEW_TAGS = "'race', 'workout', 'long_run', 'nsm_short', 'nsm_medium', 'nsm_long'"


def upgrade() -> None:
    op.drop_constraint(CONSTRAINT, "activity_tags", schema="homelab", type_="check")
    op.create_check_constraint(CONSTRAINT, "activity_tags", f"tag IN ({NEW_TAGS})", schema="homelab")


def downgrade() -> None:
    op.execute("DELETE FROM homelab.activity_tags WHERE tag IN ('nsm_short', 'nsm_medium', 'nsm_long')")
    op.drop_constraint(CONSTRAINT, "activity_tags", schema="homelab", type_="check")
    op.create_check_constraint(CONSTRAINT, "activity_tags", f"tag IN ({OLD_TAGS})", schema="homelab")
