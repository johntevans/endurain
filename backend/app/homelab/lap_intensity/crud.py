"""CRUD for lap intensity: effective values, owner overrides and quality totals.

Only the activity's owner reads or changes overrides; everyone else sees the
laps exactly as upstream serves them.
"""

from collections.abc import Iterable
from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

import activities.activity.models as activities_models
import activities.activity_laps.models as laps_models
import core.logger as core_logger
from homelab.lap_intensity import schema as intensity_schema
from homelab.lap_intensity.models import LapIntensityOverride

Activity = activities_models.Activity
Lap = laps_models.ActivityLaps


def _internal_server_error(err: Exception, context: str) -> HTTPException:
    core_logger.print_to_log(f"Error in {context}: {err}", "error", exc=err)
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Internal Server Error",
    )


def _not_found(what: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{what} not found")


def _read(lap_id: int, override: str | None, recorded: str | None) -> intensity_schema.LapIntensityRead:
    intensity, source = intensity_schema.effective_intensity(override, recorded)
    return intensity_schema.LapIntensityRead(lap_id=lap_id, intensity=intensity, recorded=recorded, source=source)


def get_activity_lap_intensities(
    activity_id: int,
    owner_user_id: int,
    db: Session,
) -> list[intensity_schema.LapIntensityRead]:
    """Get the effective intensity of every lap of one of the owner's activities.

    Args:
        activity_id: The activity.
        owner_user_id: The authenticated user; must own the activity.
        db: Database session.

    Returns:
        One entry per lap, in lap order.

    Raises:
        HTTPException: 404 when the activity does not exist or is not the
            user's, 500 on database error.
    """
    try:
        owned = db.execute(
            select(Activity.id).where(Activity.id == activity_id, Activity.user_id == owner_user_id)
        ).scalar_one_or_none()
        if owned is None:
            raise _not_found("Activity")
        rows = db.execute(
            select(Lap.id, Lap.intensity, LapIntensityOverride.intensity.label("override"))
            .outerjoin(LapIntensityOverride, LapIntensityOverride.lap_id == Lap.id)
            .where(Lap.activity_id == activity_id)
            .order_by(Lap.start_time, Lap.id)
        ).all()
        return [_read(row.id, row.override, row.intensity) for row in rows]
    except SQLAlchemyError as err:
        raise _internal_server_error(err, "get_activity_lap_intensities") from err


def set_lap_intensity(
    lap_id: int,
    intensity: intensity_schema.LapIntensityKey | None,
    owner_user_id: int,
    db: Session,
) -> intensity_schema.LapIntensityRead:
    """Set or clear the override on one lap of one of the owner's activities.

    Args:
        lap_id: The lap.
        intensity: The override, or ``None`` to remove it.
        owner_user_id: The authenticated user; must own the lap's activity.
        db: Database session.

    Returns:
        The lap's effective intensity after the change.

    Raises:
        HTTPException: 404 when the lap does not exist or is not the user's
            (no hint either way), 500 on database error.
    """
    try:
        recorded_row = db.execute(
            select(Lap.intensity)
            .join(Activity, Activity.id == Lap.activity_id)
            .where(Lap.id == lap_id, Activity.user_id == owner_user_id)
        ).first()
        if recorded_row is None:
            raise _not_found("Lap")

        if intensity is None:
            db.execute(delete(LapIntensityOverride).where(LapIntensityOverride.lap_id == lap_id))
        else:
            existing = db.get(LapIntensityOverride, lap_id)
            if existing is None:
                db.add(LapIntensityOverride(lap_id=lap_id, intensity=intensity.value))
            else:
                existing.intensity = intensity.value
        db.commit()
        return _read(lap_id, intensity.value if intensity else None, recorded_row.intensity)
    except SQLAlchemyError as err:
        db.rollback()
        raise _internal_server_error(err, "set_lap_intensity") from err


@dataclass(frozen=True)
class QualityTotals:
    """Summed quality laps of one activity."""

    timer_time: float
    distance: float


def get_quality_totals(activity_ids: Iterable[int], db: Session) -> dict[int, QualityTotals]:
    """Sum the quality laps (effective intensity active or interval) of activities.

    The caller decides which activities are quality sessions (by tag); this
    only adds up their laps. Lap time is timer time, else elapsed time.
    Activities without any laps are left out of the result, so the caller can
    count them whole.

    Args:
        activity_ids: Activities to sum.
        db: Database session.

    Returns:
        Totals by activity id, for activities that have laps.
    """
    ids = list(dict.fromkeys(activity_ids))
    if not ids:
        return {}
    rows = db.execute(
        select(
            Lap.activity_id,
            Lap.intensity,
            Lap.total_timer_time,
            Lap.total_elapsed_time,
            Lap.total_distance,
            LapIntensityOverride.intensity.label("override"),
        )
        .outerjoin(LapIntensityOverride, LapIntensityOverride.lap_id == Lap.id)
        .where(Lap.activity_id.in_(ids))
    ).all()
    time: dict[int, float] = {}
    distance: dict[int, float] = {}
    for row in rows:
        time.setdefault(row.activity_id, 0.0)
        distance.setdefault(row.activity_id, 0.0)
        intensity, _ = intensity_schema.effective_intensity(row.override, row.intensity)
        if intensity not in intensity_schema.QUALITY_INTENSITIES:
            continue
        lap_time = row.total_timer_time if row.total_timer_time is not None else row.total_elapsed_time
        time[row.activity_id] += max(float(lap_time or 0), 0.0)
        distance[row.activity_id] += max(float(row.total_distance or 0), 0.0)
    return {activity_id: QualityTotals(time[activity_id], distance[activity_id]) for activity_id in time}
