"""Read gear mileage from upstream's tables. Nothing is stored."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

import activities.activity.models as activity_models
import core.decorators as core_decorators
import gears.gear.models as gears_models
from homelab.gear_mileage import schema as mileage_schema


@core_decorators.handle_db_errors
def get_gear_mileage(user_id: int, db: Session) -> list[mileage_schema.GearMileageRead]:
    """
    Total distance of each of a user's gears, in one query.

    Upstream only totals one gear at a time, for its detail endpoint
    (``gears.gear.router.read_gear_id``). This sums the same things, so a list
    row and the gear's own page show the same number.

    Args:
        user_id: Owner user ID.
        db: Database session.

    Returns:
        One entry per gear, including gear with no activities.

    Raises:
        HTTPException: If a database error occurs.
    """
    stmt = (
        select(
            gears_models.Gear.id,
            gears_models.Gear.initial_kms,
            func.coalesce(func.sum(activity_models.Activity.distance), 0),
        )
        .outerjoin(
            activity_models.Activity,
            activity_models.Activity.gear_id == gears_models.Gear.id,
        )
        .where(gears_models.Gear.user_id == user_id)
        .group_by(gears_models.Gear.id, gears_models.Gear.initial_kms)
    )
    return [
        mileage_schema.GearMileageRead(
            gear_id=gear_id,
            total_distance=float(activities_distance) + float(initial_kms or 0) * 1000,
        )
        for gear_id, initial_kms, activities_distance in db.execute(stmt).all()
    ]
