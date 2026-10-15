"""All homelab fork API routes, registered with one line in ``core/routes.py``."""

from fastapi import APIRouter, Depends

import auth.dependencies as auth_dependencies
import core.config as core_config
from homelab.activity_tags import public_router as activity_tags_public_router
from homelab.activity_tags import router as activity_tags_router

router = APIRouter()

router.include_router(
    activity_tags_router.router,
    prefix=core_config.ROOT_PATH + "/homelab/activity_tags",
    tags=["homelab_activity_tags"],
    dependencies=[Depends(auth_dependencies.validate_access_token)],
)
router.include_router(
    activity_tags_public_router.router,
    prefix=core_config.ROOT_PATH + "/public/homelab/activity_tags",
    tags=["homelab_public_activity_tags"],
)
