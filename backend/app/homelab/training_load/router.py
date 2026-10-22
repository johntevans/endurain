"""Authenticated training-load routes (homelab fork).

Mounted at ``/api/v1/homelab/training_load`` by ``homelab.routes``. Always the
requester's own data: an activity of anyone else's gets 404.
"""

from collections.abc import Callable
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Security, status
from sqlalchemy.orm import Session

import auth.dependencies as auth_dependencies
import core.database as core_database
from homelab.training_load import crud as load_crud
from homelab.training_load import fitness_crud
from homelab.training_load import schema as load_schema

# Same cap as the training log: a year of days plus the edges.
MAX_RANGE_DAYS = 400

router = APIRouter()


@router.get(
    "",
    response_model=load_schema.ActivityLoadRead,
)
async def read_activity_load(
    activity_id: Annotated[int, Query(ge=1, description="Activity ID")],
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["activities:read"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
) -> load_schema.ActivityLoadRead:
    """Training load of one of the requester's activities (computed on first read)."""
    return load_crud.get_activity_load(activity_id, token_user_id, db)


@router.get(
    "/fitness",
    response_model=load_schema.FitnessRead,
)
async def read_fitness(
    start_date: Annotated[date, Query(description="Inclusive first local date")],
    end_date: Annotated[date, Query(description="Inclusive last local date")],
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["activities:read"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
) -> load_schema.FitnessRead:
    """The requester's daily fitness, fatigue and form between two local dates."""
    if end_date < start_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="end_date must not be before start_date",
        )
    if (end_date - start_date).days >= MAX_RANGE_DAYS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"The range may span at most {MAX_RANGE_DAYS} days",
        )
    return fitness_crud.get_fitness(token_user_id, start_date, end_date, db)
