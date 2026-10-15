"""Authenticated activity-tag routes (homelab fork).

Mounted at ``/api/v1/homelab/activity_tags`` by ``homelab.routes``.
"""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Security
from pydantic import Field
from sqlalchemy.orm import Session

import activities.activity.dependencies as activities_dependencies
import auth.dependencies as auth_dependencies
import core.database as core_database
from homelab.activity_tags import crud as tags_crud
from homelab.activity_tags import schema as tags_schema

# A list page holds at most 100 activities (server setting num_records_per_page).
MAX_IDS_PER_REQUEST = 100

ActivityIdsQuery = Annotated[
    list[Annotated[int, Field(ge=0)]],
    Query(
        alias="activity_id",
        min_length=1,
        max_length=MAX_IDS_PER_REQUEST,
        description="Activity ids (repeat the parameter); unknown or invisible ones are left out",
    ),
]

router = APIRouter()


@router.get(
    "",
    response_model=list[tags_schema.ActivityTagsRead],
)
async def read_activities_tags(
    activity_ids: ActivityIdsQuery,
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["activities:read"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
) -> list[tags_schema.ActivityTagsRead]:
    """Tags for a batch of activities (e.g. one list page), visibility-checked."""
    return tags_crud.get_visible_activities_tags(activity_ids, token_user_id, db)


@router.put(
    "/{activity_id}",
    response_model=tags_schema.ActivityTagsRead,
)
async def edit_activity_tags(
    activity_id: int,
    tags_update: tags_schema.ActivityTagsUpdate,
    _validate_activity_id: Annotated[Callable, Depends(activities_dependencies.validate_activity_id)],
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["activities:write"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
) -> tags_schema.ActivityTagsRead:
    """Replace an activity's tags. Only the owner may; others get 404."""
    return tags_crud.set_activity_tags(activity_id, tags_update.tags, token_user_id, db)
