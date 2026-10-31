"""Authenticated gear mileage route (homelab fork).

Mounted at ``/api/v1/homelab/gear_mileage`` by ``homelab.routes``. Always the
requester's own gear.
"""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Security
from sqlalchemy.orm import Session

import auth.dependencies as auth_dependencies
import core.database as core_database
from homelab.gear_mileage import crud as mileage_crud
from homelab.gear_mileage import schema as mileage_schema

router = APIRouter()


@router.get(
    "",
    response_model=list[mileage_schema.GearMileageRead],
)
async def read_gear_mileage(
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["gears:read"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
) -> list[mileage_schema.GearMileageRead]:
    """Total distance of each of the requester's gears."""
    return mileage_crud.get_gear_mileage(token_user_id, db)
