"""Nightly HRV and sleeping-heart-rate routes (homelab fork).

Mounted at ``/api/v1/homelab/sleep_hrv`` and ``/api/v1/homelab/sleep_heart_rate``
by ``homelab.routes``. Read-only: the rows are written by the Eight Sleep sync.
Same query shape as upstream's health list endpoints (``interval``,
``page_number``, ``num_records``), plus ``/latest`` for a dashboard tile.
"""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Security
from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

import auth.dependencies as auth_dependencies
import core.database as core_database
import core.dependencies as core_dependencies
import health.constants as health_constants
import health.utils as health_utils
from homelab.eight_sleep import schema as metric_schema
from homelab.eight_sleep.models import SleepHeartRate, SleepHrv


def _metric_router(model: type, read: type[BaseModel], page: type[BaseModel]) -> APIRouter:
    """List and latest routes for one per-night table."""
    metric_router = APIRouter()

    @metric_router.get("", response_model=page)
    def read_all(
        _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["health:read"])],
        _validate_pagination: Annotated[Callable, Depends(core_dependencies.validate_pagination_values_on_query)],
        token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
        db: Annotated[Session, Depends(core_database.get_db)],
        page_number: Annotated[int | None, Query(description="Pagination page number")] = None,
        num_records: Annotated[int | None, Query(description="Number of records per page")] = None,
        interval: Annotated[health_constants.Interval | None, Query(description="Time window")] = None,
    ):
        """The owner's nights, newest first."""
        where = [model.user_id == token_user_id]
        if interval is not None:
            where.append(model.date >= health_utils.get_start_date_for_interval(interval.value))
        total = db.execute(select(func.count()).select_from(model).where(*where)).scalar_one()
        stmt = select(model).where(*where).order_by(desc(model.date))
        if page_number is not None and num_records is not None:
            stmt = stmt.offset((page_number - 1) * num_records).limit(num_records)
        records = [read.model_validate(row) for row in db.execute(stmt).scalars()]
        return page(total=total, records=records)

    @metric_router.get("/latest", response_model=read | None)
    def read_latest(
        _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["health:read"])],
        token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
        db: Annotated[Session, Depends(core_database.get_db)],
    ):
        """The most recent night, or null."""
        row = db.execute(
            select(model).where(model.user_id == token_user_id).order_by(desc(model.date)).limit(1)
        ).scalar_one_or_none()
        return read.model_validate(row) if row is not None else None

    return metric_router


hrv_router = _metric_router(SleepHrv, metric_schema.SleepHrvRead, metric_schema.SleepHrvListResponse)
heart_rate_router = _metric_router(
    SleepHeartRate, metric_schema.SleepHeartRateRead, metric_schema.SleepHeartRateListResponse
)
