"""ORM model for ``homelab.activity_tags``."""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from homelab.database import HomelabBase


class ActivityTag(HomelabBase):
    """One tag on one activity.

    The table is created by ``homelab/alembic/versions/hl0001_activity_tags.py``
    (its CHECK widened by ``hl0002_nsm_activity_tags.py``), which also adds the foreign key to ``activities.id`` (ON DELETE CASCADE).
    The FK is not declared here because upstream's ``activities`` table is in
    a different ``MetaData`` (see ``homelab.database``).

    Attributes:
        activity_id: Upstream ``activities.id``.
        tag: Stable tag key, one of ``ActivityTagKey``.
        created_at: When the tag was added.
    """

    __tablename__ = "activity_tags"
    __table_args__ = (
        CheckConstraint(
            "tag IN ('race', 'workout', 'long_run', 'nsm_short', 'nsm_medium', 'nsm_long')",
            name="activity_tags_tag_check",
        ),
        # The list filter looks activities up by tag.
        Index("ix_activity_tags_tag_activity_id", "tag", "activity_id"),
    )

    activity_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tag: Mapped[str] = mapped_column(String(32), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
