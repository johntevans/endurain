"""Scheduled Withings -> Endurain weight sync.

The same shape as the Eight Sleep sync (``homelab/eight_sleep/sync.py``),
which this deliberately mirrors:

- **recent**: the last ``RECENT_DAYS`` days, hourly and once at startup.
- **history**: every weigh-in Withings has, daily. On the first run with no
  Withings rows it is also what does the backfill.

Each run reconciles its window against what Withings returned: a day's row is
created or overwritten from Withings, and a ``withings`` row whose day no
longer has a weigh-in (deleted or reassigned in the Withings app) is deleted.
A row with any other source is never deleted, and one entered by hand (no
source) is never overwritten. A failed fetch raises before anything is
written, and an empty answer for a window holding Withings rows deletes
nothing. Runs only when Withings is configured AND the owner has linked it.
"""

import os
from collections import Counter
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

import core.logger as core_logger
import core.scheduler as core_scheduler
import health.health_weight.crud as health_weight_crud
import health.health_weight.models as health_weight_models
import health.health_weight.schema as health_weight_schema
import users.users.models as users_models
from core.database import SessionLocal
from homelab.withings import client as withings_client
from homelab.withings import garmin_push as withings_garmin_push
from homelab.withings import mapping as withings_mapping
from homelab.withings import tokens as withings_tokens
from homelab.withings.models import WithingsToken

SOURCE = health_weight_schema.Source.WITHINGS.value
RECENT_DAYS = 30


def _timezone() -> str:
    return os.environ.get("TZ") or "UTC"


def _target_user_id(db: Session) -> int | None:
    ids = db.execute(select(users_models.Users.id)).scalars().all()
    if len(ids) == 1:
        return ids[0]
    linked = db.execute(select(WithingsToken.user_id)).scalars().all()
    return linked[0] if len(linked) == 1 else None


def reconcile(
    user_id: int,
    window_start: date,
    window_end: date,
    by_date: dict[date, withings_mapping.DayWeight],
    db: Session,
) -> Counter:
    """Make ``window_start..window_end`` match the Withings days. Returns counts by outcome."""
    counts: Counter = Counter()
    days = {d: v for d, v in by_date.items() if window_start <= d <= window_end}
    existing = {
        row.date: row
        for row in db.execute(
            select(health_weight_models.HealthWeight).where(
                health_weight_models.HealthWeight.user_id == user_id,
                health_weight_models.HealthWeight.date >= window_start,
                health_weight_models.HealthWeight.date <= window_end,
            )
        ).scalars()
    }
    ours = [d for d, row in existing.items() if row.source == SOURCE]
    if not days and ours:
        core_logger.print_to_log(
            f"Withings sync: empty response for {window_start}..{window_end} but "
            f"{len(ours)} Withings rows exist there; deleting nothing",
            "warning",
        )
        counts["refused empty"] += 1
        return counts

    for current in sorted(set(days) | set(existing)):
        day = days.get(current)
        row = existing.get(current)
        if day is not None:
            if row is not None and row.source is None:
                counts["manual kept"] += 1
            elif row is None:
                health_weight_crud.create_health_weight(
                    user_id, health_weight_schema.HealthWeightCreate(**day.weight.model_dump()), db
                )
                counts["created"] += 1
            else:
                health_weight_crud.edit_health_weight(
                    user_id,
                    health_weight_schema.HealthWeightUpdate(id=row.id, user_id=user_id, **day.weight.model_dump()),
                    db,
                )
                counts["updated"] += 1
        elif row is not None and row.source == SOURCE:
            health_weight_crud.delete_health_weight(user_id, row.id, db)
            counts["deleted"] += 1
    return counts


def _run(label: str, history: bool) -> None:
    if withings_client.config() is None:
        return
    try:
        with SessionLocal() as db:
            user_id = _target_user_id(db)
            if user_id is None or db.get(WithingsToken, user_id) is None:
                core_logger.print_to_log(
                    f"Withings sync ({label}) skipped: Withings is configured but not linked "
                    "(python -m homelab.withings.cli link)",
                    "warning",
                )
                return
            token = withings_tokens.access_token(user_id, db)
            tz = ZoneInfo(_timezone())
            window_end = datetime.now(tz).date()
            if history:
                groups, tz_name = withings_client.get_measure_groups(token)
            else:
                window_start = window_end - timedelta(days=RECENT_DAYS - 1)
                # A day of margin so a weigh-in near midnight lands on the right local day.
                fetch_from = datetime.combine(window_start - timedelta(days=1), time.min, tz)
                groups, tz_name = withings_client.get_measure_groups(token, start=fetch_from)
            by_date, ambiguous = withings_mapping.map_groups(groups, tz_name or _timezone())
            if history:
                oldest_ours = db.execute(
                    select(health_weight_models.HealthWeight.date)
                    .where(
                        health_weight_models.HealthWeight.user_id == user_id,
                        health_weight_models.HealthWeight.source == SOURCE,
                    )
                    .order_by(health_weight_models.HealthWeight.date)
                    .limit(1)
                ).scalar_one_or_none()
                window_start = min([*by_date, *([oldest_ours] if oldest_ours else []), window_end])
            counts = reconcile(user_id, window_start, window_end, by_date, db)
        if ambiguous:
            counts["skipped ambiguous"] += ambiguous
        summary = ", ".join(f"{n} {k}" for k, n in sorted(counts.items())) or "nothing to do"
        core_logger.print_to_log(
            f"Withings sync ({label}) {window_start}..{window_end}: {len(groups)} weigh-ins fetched; {summary}"
        )
    except Exception as err:
        core_logger.print_to_log(f"Withings sync ({label}) failed: {type(err).__name__}: {err}", "error")
        return
    if withings_garmin_push.enabled():
        _forward_to_garmin(label, user_id, groups, window_start, window_end)


def _forward_to_garmin(label: str, user_id: int, groups: list, window_start: date, window_end: date) -> None:
    # Separate from the weight sync: a Garmin failure never fails it, and the
    # next run retries, because Garmin itself is the record of what is there.
    try:
        with SessionLocal() as db:
            counts, _ = withings_garmin_push.push(user_id, groups, window_start, window_end, db)
        summary = ", ".join(f"{n} {k}" for k, n in sorted(counts.items())) or "nothing to do"
        core_logger.print_to_log(f"Withings to Garmin ({label}) {window_start}..{window_end}: {summary}")
    except Exception as err:
        core_logger.print_to_log(f"Withings to Garmin ({label}) failed: {type(err).__name__}: {err}", "error")


def sync_recent() -> None:
    """Re-sync the last ``RECENT_DAYS`` days."""
    _run("recent", history=False)


def sync_history() -> None:
    """Re-sync every weigh-in Withings has."""
    _run("history", history=True)


def _has_rows() -> bool:
    with SessionLocal() as db:
        return (
            db.execute(
                select(health_weight_models.HealthWeight.id)
                .where(health_weight_models.HealthWeight.source == SOURCE)
                .limit(1)
            ).scalar_one_or_none()
            is not None
        )


def register_jobs() -> None:
    """Add the jobs to upstream's scheduler. A no-op when Withings is not configured."""
    if withings_client.config() is None:
        return
    core_scheduler.add_scheduler_job(sync_recent, "interval", 60, [], "sync Withings weight for the last 30 days")
    core_scheduler.add_scheduler_job(sync_history, "interval", 1440, [], "sync the full Withings weight history")
    try:
        startup = sync_recent if _has_rows() else sync_history
    except Exception as err:
        core_logger.print_to_log(f"Withings sync: startup check failed: {type(err).__name__}", "error")
        startup = sync_recent
    core_scheduler.scheduler.add_job(
        startup,
        "date",
        id="homelab_withings_startup",
        replace_existing=True,
        misfire_grace_time=None,
    )
