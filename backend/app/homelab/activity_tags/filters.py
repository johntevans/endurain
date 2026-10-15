"""SQL helpers that let upstream activity queries filter by tag.

Kept here, and free of upstream imports other than the Activity model, so the
upstream CRUD only needs a one-line call per query.
"""

from collections.abc import Iterable, Sequence

from sqlalchemy import Select, distinct, func, select

import activities.activity.models as activities_models
from homelab.activity_tags.models import ActivityTag

# What upstream CRUD accepts for its ``tags`` filter (ActivityTagKey is a str).
TagList = Sequence[str]


def activity_ids_with_all_tags(tags: Iterable[str]) -> Select:
    """Select the ids of activities that carry every one of ``tags``.

    Args:
        tags: Tag keys; duplicates are ignored.

    Returns:
        A ``SELECT activity_id`` subquery usable in ``IN (...)``.
    """
    unique = sorted({str(tag) for tag in tags})
    return (
        select(ActivityTag.activity_id)
        .where(ActivityTag.tag.in_(unique))
        .group_by(ActivityTag.activity_id)
        .having(func.count(distinct(ActivityTag.tag)) == len(unique))
    )


def apply_tag_filter(stmt, tags: Iterable[str] | None):
    """Restrict an activities ``select`` to activities with ALL ``tags``.

    Args:
        stmt: A ``select()`` over ``activities``.
        tags: Tag keys to require, or ``None``/empty for no filter.

    Returns:
        The statement, filtered when tags were given.
    """
    tag_list = list(tags or [])
    if not tag_list:
        return stmt
    return stmt.where(activities_models.Activity.id.in_(activity_ids_with_all_tags(tag_list)))
