"""Authenticated lap-intensity routes (homelab fork).

Mounted at ``/api/v1/homelab/lap_intensity`` by ``homelab.routes``. Both are
owner-only; anyone else gets 404.
"""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Security
from sqlalchemy.orm import Session

import auth.dependencies as auth_dependencies
import core.database as core_database
from homelab.lap_intensity import crud as intensity_crud
from homelab.lap_intensity import schema as intensity_schema

router = APIRouter()


@router.get(
    "",
    response_model=list[intensity_schema.LapIntensityRead],
)
async def read_activity_lap_intensities(
    activity_id: Annotated[int, Query(ge=1, description="Activity ID")],
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["activities:read"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
) -> list[intensity_schema.LapIntensityRead]:
    """Effective intensity of each lap of one of the requester's activities."""
    return intensity_crud.get_activity_lap_intensities(activity_id, token_user_id, db)


@router.put(
    "/{lap_id}",
    response_model=intensity_schema.LapIntensityRead,
)
async def edit_lap_intensity(
    lap_id: int,
    update: intensity_schema.LapIntensityUpdate,
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["activities:write"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
) -> intensity_schema.LapIntensityRead:
    """Set (or, with null, clear) the override on one lap."""
    return intensity_crud.set_lap_intensity(lap_id, update.intensity, token_user_id, db)
