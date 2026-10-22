"""Fitness, fatigue and form for one user, computed on request from the cached loads.

Nothing here is stored: the series is rebuilt from ``homelab.activity_loads``
every time, from ``crud.LOAD_START`` (where it starts at zero) to the last
day asked for. Days are the activities' own local dates, as in the training
log; hidden activities (duplicates waiting for review) are left out.
"""

from datetime import UTC, date, datetime, time, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

import activities.activity.models as activities_models
import core.logger as core_logger
from homelab.training_load import crud as load_crud
from homelab.training_load import fitness
from homelab.training_load import schema as load_schema
from homelab.training_load.models import ActivityLoad
from homelab.training_log.crud import to_local

Activity = activities_models.Activity

# The latest local date starts no later than this after its UTC midnight (UTC-12).
_UTC_PAD_AFTER = timedelta(hours=12)


def get_fitness(user_id: int, start_date: date, end_date: date, db: Session) -> load_schema.FitnessRead:
    """
    Get a user's daily fitness, fatigue and form between two local dates.

    Args:
        user_id: Owner (and requester).
        start_date: Inclusive first local date.
        end_date: Inclusive last local date; future days show the decay.
        db: Database session.

    Returns:
        The days from ``max(start_date, loads start)`` to ``end_date``; none
        without thresholds.

    Raises:
        HTTPException: 500 on database error.
    """
    loads_start = load_crud.LOAD_START.date()
    if load_crud.get_settings(user_id, db) is None:
        return load_schema.FitnessRead(loads_start=loads_start, has_settings=False, days=[])
    try:
        utc_to = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=UTC) + _UTC_PAD_AFTER
        in_range = (
            Activity.user_id == user_id,
            Activity.is_hidden.is_(False),
            Activity.start_time >= load_crud.LOAD_START,
            Activity.start_time < utc_to,
        )
        ids = db.scalars(select(Activity.id).where(*in_range)).all()
        load_crud.ensure_loads(user_id, ids, db)
        rows = db.execute(
            select(
                Activity.start_time,
                Activity.timezone,
                ActivityLoad.activity_type,
                ActivityLoad.load,
                ActivityLoad.hr_load,
            )
            .join(ActivityLoad, ActivityLoad.activity_id == Activity.id)
            .where(*in_range)
        ).all()
    except SQLAlchemyError as err:
        core_logger.print_to_log(f"Error in get_fitness: {err}", "error", exc=err)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err

    inputs = fitness.daily_inputs(
        fitness.ActivityInput(
            local_date=to_local(row.start_time, row.timezone).date(),
            activity_type=row.activity_type,
            load=row.load,
            hr_load=row.hr_load,
        )
        for row in rows
    )
    days = fitness.fitness_series(inputs, loads_start, max(start_date, loads_start), end_date)
    return load_schema.FitnessRead(
        loads_start=loads_start,
        has_settings=True,
        days=[load_schema.FitnessDayRead.from_day(day) for day in days],
    )
