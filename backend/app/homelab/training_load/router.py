"""Authenticated training-load routes (homelab fork).

Mounted at ``/api/v1/homelab/training_load`` by ``homelab.routes``. Owner-only;
anyone else gets 404.
"""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Security
from sqlalchemy.orm import Session

import auth.dependencies as auth_dependencies
import core.database as core_database
from homelab.training_load import crud as load_crud
from homelab.training_load import schema as load_schema

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
