"""Queries behind the training log.

The log is the owner's own view, so every query is scoped to one user and
skips hidden activities (duplicates waiting for review). Days are bucketed by
each activity's local date, which the database cannot compute portably, so
the SQL range is padded by the widest UTC offsets and trimmed in Python.
"""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException, status
from sqlalchemy import Select, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

import activities.activity.models as activities_models
import core.config as core_config
import core.logger as core_logger
from homelab.activity_tags import schema as tags_schema
from homelab.activity_tags.models import ActivityTag
from homelab.training_log import schema as training_log_schema

# UTC offsets run from -12:00 to +14:00, so a local date D starts no earlier
# than D 00:00 - 14h UTC and ends no later than D+1 00:00 + 12h UTC.
_UTC_PAD_BEFORE = timedelta(hours=14)
_UTC_PAD_AFTER = timedelta(hours=12)

Activity = activities_models.Activity


def _internal_server_error(err: Exception, context: str) -> HTTPException:
    core_logger.print_to_log(f"Error in {context}: {err}", "error", exc=err)
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Internal Server Error",
    )


def _zone(tz_name: str | None) -> ZoneInfo:
    """The activity's zone, falling back to the server's for missing or unknown names."""
    if tz_name:
        try:
            return ZoneInfo(tz_name)
        except (ZoneInfoNotFoundError, ValueError):
            pass
    return ZoneInfo(core_config.settings.TZ)


def to_local(start_time: datetime, tz_name: str | None) -> datetime:
    """Convert a stored start time (UTC, possibly naive on SQLite) to local time."""
    if start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=UTC)
    return start_time.astimezone(_zone(tz_name))


def _owned_visible(user_id: int) -> Select:
    """The user's own, non-hidden activities."""
    return select(Activity.id).where(
        Activity.user_id == user_id,
        Activity.is_hidden.is_(False),
    )


def get_training_log_activities(
    user_id: int,
    start_date: date,
    end_date: date,
    db: Session,
) -> list[training_log_schema.TrainingLogActivity]:
    """Get the user's activities whose local start date is in ``[start_date, end_date]``.

    Args:
        user_id: Owner (and requester).
        start_date: Inclusive first local date.
        end_date: Inclusive last local date.
        db: Database session.

    Returns:
        Activities in chronological order, each with its tags.

    Raises:
        HTTPException: 500 on database error.
    """
    utc_from = datetime.combine(start_date, time.min, tzinfo=UTC) - _UTC_PAD_BEFORE
    utc_to = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=UTC) + _UTC_PAD_AFTER
    try:
        in_window = (
            Activity.user_id == user_id,
            Activity.is_hidden.is_(False),
            Activity.start_time >= utc_from,
            Activity.start_time < utc_to,
        )
        rows = db.execute(
            select(
                Activity.id,
                Activity.name,
                Activity.activity_type,
                Activity.start_time,
                Activity.timezone,
                Activity.distance,
                Activity.total_timer_time,
                Activity.total_elapsed_time,
                Activity.elevation_gain,
            )
            .where(*in_window)
            .order_by(Activity.start_time, Activity.id)
        ).all()

        tags: dict[int, set[str]] = {}
        if rows:
            tag_rows = db.execute(
                select(ActivityTag.activity_id, ActivityTag.tag).where(
                    ActivityTag.activity_id.in_(select(Activity.id).where(*in_window))
                )
            ).all()
            for activity_id, tag in tag_rows:
                tags.setdefault(activity_id, set()).add(tag)

        result: list[training_log_schema.TrainingLogActivity] = []
        for row in rows:
            local_start = to_local(row.start_time, row.timezone)
            if not start_date <= local_start.date() <= end_date:
                continue
            result.append(
                training_log_schema.TrainingLogActivity(
                    id=row.id,
                    name=row.name or "",
                    activity_type=row.activity_type,
                    local_date=local_start.date(),
                    start_time=local_start.strftime("%Y-%m-%dT%H:%M:%S"),
                    distance=max(row.distance or 0, 0),
                    total_timer_time=float(row.total_timer_time or 0),
                    total_elapsed_time=float(row.total_elapsed_time or 0),
                    elevation_gain=row.elevation_gain,
                    tags=tags_schema.sort_tags(tags.get(row.id, set())),
                )
            )
        return result
    except SQLAlchemyError as err:
        raise _internal_server_error(err, "get_training_log_activities") from err


def get_training_log_range(user_id: int, db: Session) -> training_log_schema.TrainingLogRange:
    """Get the local dates of the user's first and most recent activity.

    Args:
        user_id: Owner (and requester).
        db: Database session.

    Returns:
        The range; both dates are ``None`` when the user has no activities.

    Raises:
        HTTPException: 500 on database error.
    """
    try:
        base = select(Activity.start_time, Activity.timezone).where(
            Activity.id.in_(_owned_visible(user_id)),
        )
        first = db.execute(base.order_by(Activity.start_time.asc()).limit(1)).first()
        last = db.execute(base.order_by(Activity.start_time.desc()).limit(1)).first()
        return training_log_schema.TrainingLogRange(
            first_date=to_local(first.start_time, first.timezone).date() if first else None,
            last_date=to_local(last.start_time, last.timezone).date() if last else None,
        )
    except SQLAlchemyError as err:
        raise _internal_server_error(err, "get_training_log_range") from err
