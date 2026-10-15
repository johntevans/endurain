"""Public (unauthenticated) activity-tag routes (homelab fork).

Mounted at ``/api/v1/public/homelab/activity_tags`` by ``homelab.routes``.
Serves the tags of activities reachable through a public shareable link.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

import core.database as core_database
from homelab.activity_tags import crud as tags_crud
from homelab.activity_tags import schema as tags_schema
from homelab.activity_tags.router import ActivityIdsQuery

router = APIRouter()


@router.get(
    "",
    response_model=list[tags_schema.ActivityTagsRead],
)
async def read_public_activities_tags(
    activity_ids: ActivityIdsQuery,
    db: Annotated[Session, Depends(core_database.get_db)],
) -> list[tags_schema.ActivityTagsRead]:
    """Tags for public, shareable activities; others are left out."""
    return tags_crud.get_public_activities_tags(activity_ids, db)
