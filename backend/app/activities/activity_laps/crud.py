"""Activity laps CRUD operations."""

from sqlalchemy import select
from sqlalchemy.orm import Session

import activities.activity.crud as activity_crud
import activities.activity.models as activity_models
import activities.activity.schema as activity_schema
import activities.activity_laps.gap as activity_laps_gap
import activities.activity_laps.models as activity_laps_models
import activities.activity_laps.schema as activity_laps_schema
import activities.activity_streams.constants as activity_streams_constants
import activities.activity_streams.models as activity_streams_models
import core.decorators as core_decorators
import server_settings.utils as server_settings_utils

_LAP_COLUMNS: tuple[str, ...] = (
    "start_time",
    "start_position_lat",
    "start_position_long",
    "end_position_lat",
    "end_position_long",
    "total_elapsed_time",
    "total_timer_time",
    "total_distance",
    "total_cycles",
    "total_calories",
    "avg_heart_rate",
    "max_heart_rate",
    "avg_cadence",
    "max_cadence",
    "avg_power",
    "max_power",
    "total_ascent",
    "total_descent",
    "intensity",
    "lap_trigger",
    "sport",
    "sub_sport",
    "normalized_power",
    "total_work",
    "avg_vertical_oscillation",
    "avg_stance_time",
    "avg_fractional_cadence",
    "max_fractional_cadence",
    "enhanced_avg_pace",
    "enhanced_avg_speed",
    "enhanced_max_pace",
    "enhanced_max_speed",
    "enhanced_min_altitude",
    "enhanced_max_altitude",
    "avg_vertical_ratio",
    "avg_step_length",
)


def _to_read_schema(
    orm_lap: activity_laps_models.ActivityLaps,
    timezone: str | None,
) -> activity_laps_schema.ActivityLapsRead:
    """
    Convert an ORM ActivityLaps to a Read schema.

    Args:
        orm_lap: The ORM model instance.
        timezone: IANA timezone name from the
            parent activity.

    Returns:
        An ActivityLapsRead schema instance.
    """
    schema = activity_laps_schema.ActivityLapsRead.model_validate(orm_lap)
    schema.timezone = timezone
    return schema


def _attach_grade_adjusted_pace(
    laps: list[activity_laps_schema.ActivityLapsRead],
    activity: activity_schema.Activity,
    token_user_id: int | None,
    db: Session,
) -> None:
    """
    Fill in grade-adjusted pace/speed on laps from the activity's streams.

    Only applies to running and walking activities that have both an elevation
    and a velocity stream. For non-owners it is skipped when elevation, speed
    or pace is hidden, since GAP is derived from them.

    Args:
        laps: Lap read schemas to update in place.
        activity: The parent activity.
        token_user_id: The requesting user ID, or ``None`` for public access.
        db: Database session.
    """
    if activity.activity_type not in activity_laps_gap.GAP_ACTIVITY_TYPES:
        return
    if token_user_id != activity.user_id and (activity.hide_elevation or activity.hide_speed or activity.hide_pace):
        return

    stmt = select(activity_streams_models.ActivityStreams).where(
        activity_streams_models.ActivityStreams.activity_id == activity.id,
        activity_streams_models.ActivityStreams.stream_type.in_(
            (
                activity_streams_constants.STREAM_TYPE_ELEVATION,
                activity_streams_constants.STREAM_TYPE_SPEED,
            )
        ),
    )
    waypoints_by_type = {stream.stream_type: stream.stream_waypoints for stream in db.scalars(stmt).all()}
    velocity = waypoints_by_type.get(activity_streams_constants.STREAM_TYPE_SPEED)
    elevation = waypoints_by_type.get(activity_streams_constants.STREAM_TYPE_ELEVATION)
    if not velocity or not elevation:
        return

    ordered = sorted(laps, key=lambda lap: lap.start_time)
    ratios = activity_laps_gap.compute_laps_gap_ratio(
        [(lap.start_time, lap.total_elapsed_time) for lap in ordered],
        velocity,
        elevation,
    )
    for lap, ratio in zip(ordered, ratios, strict=True):
        speed = lap.enhanced_avg_speed
        if speed is None and lap.enhanced_avg_pace:
            speed = 1 / lap.enhanced_avg_pace
        if ratio is None or not speed or speed <= 0:
            continue
        gap_speed = speed * ratio
        lap.grade_adjusted_avg_speed = gap_speed
        lap.grade_adjusted_avg_pace = 1 / gap_speed


@core_decorators.handle_db_errors
def get_activity_laps(
    activity_id: int,
    token_user_id: int,
    db: Session,
) -> list[activity_laps_schema.ActivityLapsRead] | None:
    """
    Retrieve activity laps for a given activity.

    Args:
        activity_id: The activity ID.
        token_user_id: The authenticated user ID.
        db: Database session.

    Returns:
        List of ActivityLapsRead or None if not
            found or hidden.

    Raises:
        HTTPException: If database error occurs.
    """
    activity = activity_crud.get_activity_by_id(activity_id, db)

    if not activity:
        return None

    if token_user_id != activity.user_id and activity.hide_laps:
        return None

    stmt = select(activity_laps_models.ActivityLaps).where(
        activity_laps_models.ActivityLaps.activity_id == activity_id,
    )
    activity_laps = db.scalars(stmt).all()

    if not activity_laps:
        return None

    laps = [_to_read_schema(lap, activity.timezone) for lap in activity_laps]
    _attach_grade_adjusted_pace(laps, activity, token_user_id, db)
    return laps


@core_decorators.handle_db_errors
def get_activities_laps(
    activity_ids: list[int],
    token_user_id: int,
    db: Session,
    prefetched_activities: list[activity_models.Activity] | None = None,
) -> list[activity_laps_schema.ActivityLapsRead]:
    """
    Retrieve laps for multiple activities.

    Args:
        activity_ids: List of activity IDs.
        token_user_id: The authenticated user ID.
        db: Database session.
        prefetched_activities: Optional pre-fetched
            activities (avoids a re-query when the
            caller already has them in scope).

    Returns:
        List of ActivityLapsRead schemas.

    Raises:
        HTTPException: If database error occurs.
    """
    if not activity_ids:
        return []

    activities_list = prefetched_activities
    if not activities_list:
        stmt = select(activity_models.Activity).where(activity_models.Activity.id.in_(activity_ids))
        activities_list = db.scalars(stmt).all()

    if not activities_list:
        return []

    activity_map = {activity.id: activity for activity in activities_list}

    allowed_ids = [activity.id for activity in activities_list if activity.user_id == token_user_id]

    if not allowed_ids:
        return []

    stmt = select(activity_laps_models.ActivityLaps).where(
        activity_laps_models.ActivityLaps.activity_id.in_(allowed_ids)
    )
    activity_laps = db.scalars(stmt).all()

    if not activity_laps:
        return []

    return [
        _to_read_schema(
            lap,
            activity_map[lap.activity_id].timezone,
        )
        for lap in activity_laps
    ]


@core_decorators.handle_db_errors
def get_public_activity_laps(
    activity_id: int,
    db: Session,
) -> list[activity_laps_schema.ActivityLapsRead] | None:
    """
    Retrieve public activity laps for an activity.

    Args:
        activity_id: The activity ID.
        db: Database session.

    Returns:
        List of ActivityLapsRead or None if not
            found, hidden, or not publicly visible.

    Raises:
        HTTPException: If database error occurs.
    """
    activity = activity_crud.get_activity_by_id(activity_id, db)

    if not activity:
        return None

    if activity.hide_laps:
        return None

    server_settings = server_settings_utils.get_server_settings_or_404(db)

    if not server_settings.public_shareable_links:
        return None

    if activity.visibility != 0:
        return None

    stmt = select(activity_laps_models.ActivityLaps).where(
        activity_laps_models.ActivityLaps.activity_id == activity_id,
    )
    activity_laps = db.scalars(stmt).all()

    if not activity_laps:
        return None

    laps = [_to_read_schema(lap, activity.timezone) for lap in activity_laps]
    _attach_grade_adjusted_pace(laps, activity, None, db)
    return laps


@core_decorators.handle_db_errors
def create_activity_laps(
    activity_laps: list[dict],
    activity_id: int,
    db: Session,
) -> None:
    """
    Bulk create activity laps for an activity.

    Args:
        activity_laps: List of lap dicts from
            file parsers.
        activity_id: The parent activity ID.
        db: Database session.

    Returns:
        None.

    Raises:
        HTTPException: If database error occurs.
    """
    laps = [
        activity_laps_models.ActivityLaps(
            activity_id=activity_id,
            **{key: lap.get(key) for key in _LAP_COLUMNS},
        )
        for lap in activity_laps
    ]

    db.add_all(laps)
    db.commit()
