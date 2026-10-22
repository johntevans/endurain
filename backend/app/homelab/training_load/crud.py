"""Training load: computing, caching and reading each activity's load.

Loads live in ``homelab.activity_loads`` as a cache. Readers call
``ensure_loads``, which computes any of the requested activities that have no
row yet (a new import) or whose row is stale (the settings or the activity's
type changed since), so no upstream import path needs a hook. Only activities
from ``LOAD_START`` on get a load; ``cli backfill`` fills them in bulk.
"""

from collections.abc import Iterable, Sequence
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

import activities.activity.models as activities_models
import activities.activity_streams.constants as streams_constants
import activities.activity_streams.models as streams_models
import core.logger as core_logger
import users.users.models as users_models
from homelab.training_load import calculate
from homelab.training_load import schema as load_schema
from homelab.training_load.models import ActivityLoad, TrainingLoadSettings

Activity = activities_models.Activity
Streams = streams_models.ActivityStreams

# Activities that start before this get no load (yet): the backfill covered
# 2026 only. Moving it earlier and running ``cli backfill --since`` extends it.
LOAD_START = datetime(2026, 1, 1, tzinfo=UTC)

# At most this many loads are computed while serving one request; the rest
# follow on the next. Only a settings change without a recompute gets here.
MAX_COMPUTED_PER_REQUEST = 50

_STREAM_KEYS = {
    streams_constants.STREAM_TYPE_HR: "hr",
    streams_constants.STREAM_TYPE_SPEED: "vel",
    streams_constants.STREAM_TYPE_ELEVATION: "ele",
}


def _aware(value: datetime) -> datetime:
    # SQLite hands back naive datetimes; they are UTC.
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _internal_server_error(err: Exception, context: str) -> HTTPException:
    core_logger.print_to_log(f"Error in {context}: {err}", "error", exc=err)
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Internal Server Error",
    )


def get_settings(user_id: int, db: Session) -> TrainingLoadSettings | None:
    """The user's thresholds, or ``None`` when they have not set any."""
    return db.get(TrainingLoadSettings, user_id)


def thresholds(settings: TrainingLoadSettings, gender: str | None) -> calculate.Thresholds:
    """Turn a settings row (and the user's gender, for TRIMP) into calculator input."""
    return calculate.Thresholds(
        resting_hr=settings.resting_hr,
        threshold_hr=settings.threshold_hr,
        max_hr=settings.max_hr,
        threshold_speed=1000.0 / settings.threshold_pace,
        gender="female" if gender == "female" else "male",
    )


def user_gender(user_id: int, db: Session) -> str | None:
    """The user's gender (TRIMP's constants differ by sex)."""
    return db.execute(select(users_models.Users.gender).where(users_models.Users.id == user_id)).scalar_one_or_none()


def _streams(activity_ids: Sequence[int], db: Session) -> dict[int, dict[str, list[dict]]]:
    rows = db.execute(
        select(Streams.activity_id, Streams.stream_type, Streams.stream_waypoints).where(
            Streams.activity_id.in_(activity_ids),
            Streams.stream_type.in_(_STREAM_KEYS),
        )
    ).all()
    result: dict[int, dict[str, list[dict]]] = {}
    for activity_id, stream_type, waypoints in rows:
        result.setdefault(activity_id, {})[_STREAM_KEYS[stream_type]] = waypoints or []
    return result


def compute_loads(
    activities: Sequence[Activity],
    settings: TrainingLoadSettings,
    gender: str | None,
    existing: dict[int, ActivityLoad],
    db: Session,
) -> dict[int, ActivityLoad]:
    """
    Compute and stage (not commit) the loads of some activities.

    Args:
        activities: Activities of the settings' owner.
        settings: Their thresholds.
        gender: The owner's gender.
        existing: Rows already stored for any of them, updated in place.
        db: Database session.

    Returns:
        The rows by activity id.
    """
    if not activities:
        return {}
    athlete = thresholds(settings, gender)
    streams = _streams([activity.id for activity in activities], db)
    now = datetime.now(UTC)
    rows: dict[int, ActivityLoad] = {}
    for activity in activities:
        timer = float(activity.total_timer_time or 0) or float(activity.total_elapsed_time or 0)
        result = calculate.activity_load(
            activity.activity_type,
            timer,
            float(max(activity.distance or 0, 0)),
            streams.get(activity.id, {}),
            athlete,
        )
        row = existing.get(activity.id)
        if row is None:
            row = ActivityLoad(activity_id=activity.id)
            db.add(row)
        row.load = result.load
        row.source = result.source.value
        row.pace_load = result.pace_load
        row.hr_load = result.hr_load
        row.activity_type = activity.activity_type
        row.computed_at = now
        rows[activity.id] = row
    return rows


def _is_stale(row: ActivityLoad, activity: Activity, settings: TrainingLoadSettings) -> bool:
    return row.activity_type != activity.activity_type or _aware(row.computed_at) < _aware(settings.updated_at)


def _snapshot(rows: Iterable[ActivityLoad]) -> dict[int, load_schema.ActivityLoadRead]:
    # Taken before any commit, which would expire the rows (a query each).
    return {row.activity_id: load_schema.ActivityLoadRead.from_row(row.activity_id, row) for row in rows}


def ensure_loads(user_id: int, activity_ids: Iterable[int], db: Session) -> dict[int, load_schema.ActivityLoadRead]:
    """
    Get the loads of some of a user's activities, computing missing or stale ones.

    Never raises: a failure to compute is logged and the stored rows are
    returned, so a load problem cannot take down the page that shows it.

    Args:
        user_id: Owner of the activities (others' ids are ignored).
        activity_ids: Activities wanted.
        db: Database session; computed rows are committed.

    Returns:
        Loads by activity id, for the activities that have (or now have) one.
        Empty when the user has no settings.
    """
    ids = list(dict.fromkeys(activity_ids))
    if not ids:
        return {}
    try:
        settings = get_settings(user_id, db)
        if settings is None:
            return {}
        activities = db.scalars(
            select(Activity).where(
                Activity.id.in_(ids),
                Activity.user_id == user_id,
                Activity.start_time >= LOAD_START,
            )
        ).all()
        if not activities:
            return {}
        stored = {
            row.activity_id: row
            for row in db.scalars(
                select(ActivityLoad).where(ActivityLoad.activity_id.in_([a.id for a in activities]))
            ).all()
        }
        todo = [a for a in activities if a.id not in stored or _is_stale(stored[a.id], a, settings)]
        todo = todo[:MAX_COMPUTED_PER_REQUEST]
        if todo:
            stored.update(compute_loads(todo, settings, user_gender(user_id, db), stored, db))
        result = _snapshot(stored.values())
        if todo:
            db.commit()
        return result
    except SQLAlchemyError as err:
        db.rollback()
        core_logger.print_to_log(f"Error in ensure_loads: {err}", "error", exc=err)
        try:
            return _snapshot(db.scalars(select(ActivityLoad).where(ActivityLoad.activity_id.in_(ids))).all())
        except SQLAlchemyError:
            return {}


def get_activity_load(activity_id: int, owner_user_id: int, db: Session) -> load_schema.ActivityLoadRead:
    """
    Get one of the owner's activities' load.

    Args:
        activity_id: The activity.
        owner_user_id: The authenticated user; must own it.
        db: Database session.

    Returns:
        Its load; every value ``None`` when it has none (no settings, before
        ``LOAD_START``).

    Raises:
        HTTPException: 404 when the activity does not exist or is not the
            user's, 500 on database error.
    """
    try:
        owned = db.execute(
            select(Activity.id).where(Activity.id == activity_id, Activity.user_id == owner_user_id)
        ).scalar_one_or_none()
    except SQLAlchemyError as err:
        raise _internal_server_error(err, "get_activity_load") from err
    if owned is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Activity not found")
    return ensure_loads(owner_user_id, [activity_id], db).get(activity_id) or load_schema.ActivityLoadRead(
        activity_id=activity_id
    )
