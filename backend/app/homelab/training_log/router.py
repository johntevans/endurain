"""Authenticated training-log routes (homelab fork).

Mounted at ``/api/v1/homelab/training_log`` by ``homelab.routes``. The log is
always the requester's own: there is no user id in the path.
"""

from collections.abc import Callable
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Security, status
from sqlalchemy.orm import Session

import auth.dependencies as auth_dependencies
import core.database as core_database
from homelab.training_log import crud as training_log_crud
from homelab.training_log import schema as training_log_schema

# The frontend asks for one year of week rows at a time: up to 53 weeks plus
# the partial weeks at either end.
MAX_RANGE_DAYS = 400

router = APIRouter()


@router.get(
    "",
    response_model=list[training_log_schema.TrainingLogActivity],
)
async def read_training_log(
    start_date: Annotated[date, Query(description="Inclusive first local date")],
    end_date: Annotated[date, Query(description="Inclusive last local date")],
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["activities:read"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
) -> list[training_log_schema.TrainingLogActivity]:
    """The requester's activities between two local dates, with their tags."""
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
    return training_log_crud.get_training_log_activities(token_user_id, start_date, end_date, db)


@router.get(
    "/range",
    response_model=training_log_schema.TrainingLogRange,
)
async def read_training_log_range(
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["activities:read"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
) -> training_log_schema.TrainingLogRange:
    """Local dates of the requester's first and last activity (which years to show)."""
    return training_log_crud.get_training_log_range(token_user_id, db)
