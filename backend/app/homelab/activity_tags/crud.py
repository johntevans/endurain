"""CRUD for activity tags.

Visibility follows the activity's own: whoever may see an activity may see its
tags, using upstream's visibility condition so the two never drift. Only the
owner may change them.
"""

from collections.abc import Iterable

from fastapi import HTTPException, status
from sqlalchemy import delete, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

import activities.activity.crud as activities_crud
import activities.activity.models as activities_models
import core.logger as core_logger
import server_settings.utils as server_settings_utils
from homelab.activity_tags import schema as tags_schema
from homelab.activity_tags.models import ActivityTag


def _internal_server_error(err: Exception, context: str) -> HTTPException:
    core_logger.print_to_log(f"Error in {context}: {err}", "error", exc=err)
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Internal Server Error",
    )


def _tags_by_activity(activity_ids: list[int], db: Session) -> list[tags_schema.ActivityTagsRead]:
    """Build one entry per id (in the given order), with its tags."""
    if not activity_ids:
        return []
    rows = db.execute(
        select(ActivityTag.activity_id, ActivityTag.tag).where(ActivityTag.activity_id.in_(activity_ids))
    ).all()
    tags: dict[int, set[str]] = {activity_id: set() for activity_id in activity_ids}
    for activity_id, tag in rows:
        tags[activity_id].add(tag)
    return [
        tags_schema.ActivityTagsRead(activity_id=activity_id, tags=tags_schema.sort_tags(tags[activity_id]))
        for activity_id in activity_ids
    ]


def _unique_in_order(activity_ids: Iterable[int]) -> list[int]:
    return list(dict.fromkeys(activity_ids))


def get_visible_activities_tags(
    activity_ids: Iterable[int],
    requester_user_id: int,
    db: Session,
) -> list[tags_schema.ActivityTagsRead]:
    """Get tags for the given activities that the requester may see.

    Activities the requester does not own and may not see (private, hidden,
    followers-only without an accepted follow) and ids that do not exist are
    left out of the result, exactly as the activity itself would be.

    Args:
        activity_ids: Activity ids to look up.
        requester_user_id: The authenticated user.
        db: Database session.

    Returns:
        One entry per visible activity, in request order.

    Raises:
        HTTPException: 500 on database error.
    """
    ids = _unique_in_order(activity_ids)
    try:
        visible = set(
            db.execute(
                select(activities_models.Activity.id).where(
                    activities_models.Activity.id.in_(ids),
                    or_(
                        activities_models.Activity.user_id == requester_user_id,
                        activities_crud._visible_to_requester_condition(requester_user_id),
                    ),
                )
            )
            .scalars()
            .all()
        )
        return _tags_by_activity([i for i in ids if i in visible], db)
    except SQLAlchemyError as err:
        raise _internal_server_error(err, "get_visible_activities_tags") from err


def get_public_activities_tags(
    activity_ids: Iterable[int],
    db: Session,
) -> list[tags_schema.ActivityTagsRead]:
    """Get tags for activities reachable through a public shareable link.

    Mirrors ``get_activity_by_id_if_is_public``: nothing when the server has
    public shareable links disabled, otherwise only public, non-hidden
    activities.

    Args:
        activity_ids: Activity ids to look up.
        db: Database session.

    Returns:
        One entry per public activity, in request order.

    Raises:
        HTTPException: 500 on database error.
    """
    ids = _unique_in_order(activity_ids)
    try:
        if not server_settings_utils.get_server_settings_or_404(db).public_shareable_links:
            return []
        visible = set(
            db.execute(
                select(activities_models.Activity.id).where(
                    activities_models.Activity.id.in_(ids),
                    activities_crud._visible_to_requester_condition(None),
                )
            )
            .scalars()
            .all()
        )
        return _tags_by_activity([i for i in ids if i in visible], db)
    except SQLAlchemyError as err:
        raise _internal_server_error(err, "get_public_activities_tags") from err


def set_activity_tags(
    activity_id: int,
    tags: Iterable[str],
    owner_user_id: int,
    db: Session,
) -> tags_schema.ActivityTagsRead:
    """Replace an activity's tags. Owner only.

    Tags that stay keep their ``created_at``.

    Args:
        activity_id: Activity to tag.
        tags: The complete new tag set (duplicates ignored).
        owner_user_id: The authenticated user; must own the activity.
        db: Database session.

    Returns:
        The activity's tags after the change.

    Raises:
        HTTPException: 404 when the activity does not exist or is not the
            user's (no hint either way), 500 on database error.
    """
    wanted = {str(tag) for tag in tags}
    try:
        owned = db.execute(
            select(activities_models.Activity.id).where(
                activities_models.Activity.id == activity_id,
                activities_models.Activity.user_id == owner_user_id,
            )
        ).scalar_one_or_none()
        if owned is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Activity not found",
            )

        current = set(db.execute(select(ActivityTag.tag).where(ActivityTag.activity_id == activity_id)).scalars().all())
        removed = current - wanted
        if removed:
            db.execute(
                delete(ActivityTag).where(
                    ActivityTag.activity_id == activity_id,
                    ActivityTag.tag.in_(removed),
                )
            )
        for tag in sorted(wanted - current):
            db.add(ActivityTag(activity_id=activity_id, tag=tag))
        db.commit()
        return tags_schema.ActivityTagsRead(activity_id=activity_id, tags=tags_schema.sort_tags(wanted))
    except SQLAlchemyError as err:
        db.rollback()
        raise _internal_server_error(err, "set_activity_tags") from err
