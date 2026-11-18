"""Grade-adjusted pace on the laps upstream's laps service returns.

Upstream's laps read is paged, so a page can start mid-activity. The GAP model
aligns lap windows to the streams from the activity's FIRST lap, so that lap's
start is looked up here rather than taken from the page.
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

import modules.activities.activity.models as activities_models
import modules.activities.activity_laps.gap as activity_laps_gap
import modules.activities.activity_laps.models as activity_laps_models
import modules.activities.activity_laps.schema as activity_laps_schema
import modules.activities.activity_streams.constants as activity_streams_constants
import modules.activities.activity_streams.models as activity_streams_models


def _utc(value: datetime) -> datetime:
    """Return ``value`` as an aware UTC datetime (naive values are taken as UTC)."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def attach_grade_adjusted_pace(
    laps: list[activity_laps_schema.ActivityLapsRead],
    activity_id: int,
    requester_user_id: int | None,
    db: Session,
) -> None:
    """
    Fill in grade-adjusted pace/speed on laps from the activity's streams.

    Only applies to running and walking activities that have both an elevation
    and a velocity stream. For non-owners it is skipped when elevation, speed
    or pace is hidden, since GAP is derived from them.

    Args:
        laps: Lap read schemas (one page) to update in place.
        activity_id: The parent activity.
        requester_user_id: The requesting user ID, or ``None`` for public access.
        db: Database session.
    """
    if not laps:
        return
    activity = db.get(activities_models.Activity, activity_id)
    if activity is None or activity.activity_type not in activity_laps_gap.GAP_ACTIVITY_TYPES:
        return
    if requester_user_id != activity.user_id and (activity.hide_elevation or activity.hide_speed or activity.hide_pace):
        return

    stmt = select(activity_streams_models.ActivityStreams).where(
        activity_streams_models.ActivityStreams.activity_id == activity_id,
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

    first_start = db.scalar(
        select(activity_laps_models.ActivityLaps.start_time)
        .where(activity_laps_models.ActivityLaps.activity_id == activity_id)
        .order_by(activity_laps_models.ActivityLaps.start_time)
        .limit(1)
    )
    ordered = sorted(laps, key=lambda lap: _utc(lap.start_time))
    ratios = activity_laps_gap.compute_laps_gap_ratio(
        [(_utc(lap.start_time), lap.total_elapsed_time) for lap in ordered],
        velocity,
        elevation,
        anchor=_utc(first_start) if first_start is not None else None,
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
