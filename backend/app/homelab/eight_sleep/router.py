"""Nightly HRV routes (homelab fork).

Mounted at ``/api/v1/homelab/sleep_hrv`` by ``homelab.routes``. Read-only: the
rows are written by the Eight Sleep sync. Same query shape as upstream's health
list endpoints (``interval``, ``page_number``, ``num_records``).
"""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Security
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

import auth.dependencies as auth_dependencies
import core.database as core_database
import core.dependencies as core_dependencies
import health.constants as health_constants
import health.utils as health_utils
from homelab.eight_sleep import schema as hrv_schema
from homelab.eight_sleep.models import SleepHrv

router = APIRouter()


@router.get("", response_model=hrv_schema.SleepHrvListResponse)
def read_sleep_hrv(
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["health:read"])],
    _validate_pagination: Annotated[Callable, Depends(core_dependencies.validate_pagination_values_on_query)],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
    page_number: Annotated[int | None, Query(description="Pagination page number")] = None,
    num_records: Annotated[int | None, Query(description="Number of records per page")] = None,
    interval: Annotated[health_constants.Interval | None, Query(description="Time window")] = None,
) -> hrv_schema.SleepHrvListResponse:
    """The owner's nightly HRV, newest first."""
    where = [SleepHrv.user_id == token_user_id]
    if interval is not None:
        where.append(SleepHrv.date >= health_utils.get_start_date_for_interval(interval.value))
    total = db.execute(select(func.count()).select_from(SleepHrv).where(*where)).scalar_one()
    stmt = select(SleepHrv).where(*where).order_by(desc(SleepHrv.date))
    if page_number is not None and num_records is not None:
        stmt = stmt.offset((page_number - 1) * num_records).limit(num_records)
    records = [hrv_schema.SleepHrvRead.model_validate(row) for row in db.execute(stmt).scalars()]
    return hrv_schema.SleepHrvListResponse(total=total, records=records)


@router.get("/latest", response_model=hrv_schema.SleepHrvRead | None)
def read_latest_sleep_hrv(
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["health:read"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
) -> hrv_schema.SleepHrvRead | None:
    """The most recent night with HRV, or null. Feeds the dashboard tile."""
    row = db.execute(
        select(SleepHrv).where(SleepHrv.user_id == token_user_id).order_by(desc(SleepHrv.date)).limit(1)
    ).scalar_one_or_none()
    return hrv_schema.SleepHrvRead.model_validate(row) if row is not None else None
