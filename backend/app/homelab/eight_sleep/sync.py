"""Scheduled Eight Sleep -> Endurain sleep sync.

Eight Sleep sends no change feed, so corrections made in its app (an edited
night, a deleted session) only arrive by fetching the night again. Two jobs:

- **recent**: the last ``RECENT_DAYS`` days, hourly and once at startup.
- **history**: everything back to the first recorded night, daily. On the
  first run with no Eight Sleep rows it is also what does the backfill.

Each run reconciles the whole window against what Eight Sleep returned:
rows are created or overwritten from Eight Sleep, and an ``eight_sleep`` row
whose date no longer yields a night is deleted. A row with any other source
is never deleted, and one entered by hand (no source) is never overwritten.
A failed fetch raises before anything is written, so it can never read as a
month of deletions.

Each night's HRV goes to the fork-owned ``homelab.sleep_hrv`` (upstream has no
column for it) and is reconciled over the same window: kept for every night
that imports, deleted for one that no longer does.
"""

import os
from collections import Counter
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

import core.logger as core_logger
import core.scheduler as core_scheduler
import health.health_sleep.crud as health_sleep_crud
import health.health_sleep.models as health_sleep_models
import health.health_sleep.schema as health_sleep_schema
import users.users.models as users_models
from core.database import SessionLocal
from homelab.eight_sleep import client as eight_sleep_client
from homelab.eight_sleep import mapping as eight_sleep_mapping
from homelab.eight_sleep.models import SleepHrv

SOURCE = health_sleep_schema.Source.EIGHT_SLEEP.value
RECENT_DAYS = 30
# History walks back in client-sized chunks until this many consecutive empty
# ones; well beyond any trip away from the bed.
HISTORY_EMPTY_CHUNKS_TO_STOP = 6
HISTORY_FLOOR = date(2014, 1, 1)


def _timezone() -> str:
    return os.environ.get("TZ") or "UTC"


def _target_user_id(db: Session) -> int | None:
    configured = os.environ.get("EIGHT_SLEEP_ENDURAIN_USER_ID", "").strip()
    if configured:
        return int(configured)
    user_ids = db.execute(select(users_models.Users.id)).scalars().all()
    if len(user_ids) == 1:
        return user_ids[0]
    core_logger.print_to_log(
        f"Eight Sleep sync: {len(user_ids)} users and EIGHT_SLEEP_ENDURAIN_USER_ID unset; not syncing",
        "error",
    )
    return None


def _today() -> date:
    return datetime.now().date()


def _fetch_history(tz: str) -> tuple[date, list[dict]]:
    """Walk back from today until a long run of empty chunks. Returns (window start, days)."""
    days: list[dict] = []
    chunk = eight_sleep_client.MAX_DAYS_PER_REQUEST
    end = _today()
    empty_run = 0
    start = end
    while empty_run < HISTORY_EMPTY_CHUNKS_TO_STOP and end >= HISTORY_FLOOR:
        start = max(end - timedelta(days=chunk - 1), HISTORY_FLOOR)
        found = eight_sleep_client.fetch_days(start, end, tz)
        days.extend(found)
        empty_run = 0 if found else empty_run + 1
        end = start - timedelta(days=1)
    return start, days


def reconcile(
    user_id: int,
    window_start: date,
    window_end: date,
    days: list[dict],
    tz: str,
    db: Session,
) -> Counter:
    """Make ``window_start..window_end`` match ``days``. Returns counts by outcome."""
    counts: Counter = Counter()
    results = {}
    for day in days:
        result = eight_sleep_mapping.map_day(day, tz)
        if window_start <= result.date <= window_end:
            results[result.date] = result

    existing = {
        row.date: row
        for row in db.execute(
            select(health_sleep_models.HealthSleep).where(
                health_sleep_models.HealthSleep.user_id == user_id,
                health_sleep_models.HealthSleep.date >= window_start,
                health_sleep_models.HealthSleep.date <= window_end,
            )
        ).scalars()
    }

    # An empty answer for a window we hold Eight Sleep rows in looks far more
    # like an API change than like every night having been deleted.
    ours = [d for d, row in existing.items() if row.source == SOURCE]
    if not days and ours:
        core_logger.print_to_log(
            f"Eight Sleep sync: empty response for {window_start}..{window_end} but "
            f"{len(ours)} Eight Sleep rows exist there; deleting nothing",
            "warning",
        )
        counts["refused empty"] += 1
        return counts

    for current in sorted(set(results) | set(existing)):
        result = results.get(current)
        row = existing.get(current)
        if result is not None and result.skip is eight_sleep_mapping.Skip.PROCESSING:
            counts["processing"] += 1
            continue
        if result is not None and result.sleep is not None:
            if row is not None and row.source is None:
                counts["manual kept"] += 1
                continue
            if row is None:
                health_sleep_crud.create_health_sleep(
                    user_id, health_sleep_schema.HealthSleepCreate(**result.sleep.model_dump()), db
                )
                counts["created"] += 1
            else:
                health_sleep_crud.edit_health_sleep(
                    user_id,
                    health_sleep_schema.HealthSleepUpdate(id=row.id, user_id=user_id, **result.sleep.model_dump()),
                    db,
                )
                counts["updated"] += 1
            continue
        if result is not None:
            counts[f"skipped {result.skip.value}"] += 1
        if row is not None and row.source == SOURCE:
            health_sleep_crud.delete_health_sleep(user_id, row.id, db)
            counts["deleted"] += 1
    _reconcile_hrv(user_id, window_start, window_end, results, db, counts)
    return counts


def _reconcile_hrv(
    user_id: int,
    window_start: date,
    window_end: date,
    results: dict[date, eight_sleep_mapping.DayResult],
    db: Session,
    counts: Counter,
) -> None:
    """Make ``homelab.sleep_hrv`` match the imported nights in the window."""
    existing = {
        row.date: row
        for row in db.execute(
            select(SleepHrv).where(
                SleepHrv.user_id == user_id,
                SleepHrv.date >= window_start,
                SleepHrv.date <= window_end,
            )
        ).scalars()
    }
    for current in sorted(set(results) | set(existing)):
        result = results.get(current)
        row = existing.get(current)
        if result is not None and result.skip is eight_sleep_mapping.Skip.PROCESSING:
            continue
        night = result.hrv if result is not None and result.sleep is not None else None
        if night is None:
            if row is not None:
                db.delete(row)
                counts["hrv deleted"] += 1
            continue
        if row is None:
            row = SleepHrv(user_id=user_id, date=current, source=SOURCE)
            db.add(row)
        row.hrv_ms = night.hrv_ms
        row.avg_7d_ms = night.avg_7d_ms
        row.baseline_ms = night.baseline_ms
        row.range_low_ms = night.range_low_ms
        row.range_high_ms = night.range_high_ms
        counts["hrv"] += 1
    db.commit()


def _run(label: str, history: bool) -> None:
    if not eight_sleep_client.owns_sleep():
        return
    tz = _timezone()
    try:
        with SessionLocal() as db:
            user_id = _target_user_id(db)
            if user_id is None:
                return
            window_end = _today()
            if history:
                window_start, days = _fetch_history(tz)
                oldest_ours = db.execute(
                    select(health_sleep_models.HealthSleep.date)
                    .where(
                        health_sleep_models.HealthSleep.user_id == user_id,
                        health_sleep_models.HealthSleep.source == SOURCE,
                    )
                    .order_by(health_sleep_models.HealthSleep.date)
                    .limit(1)
                ).scalar_one_or_none()
                if oldest_ours is not None:
                    window_start = min(window_start, oldest_ours)
            else:
                window_start = window_end - timedelta(days=RECENT_DAYS - 1)
                days = eight_sleep_client.fetch_days(window_start, window_end, tz)
            counts = reconcile(user_id, window_start, window_end, days, tz, db)
        summary = ", ".join(f"{n} {k}" for k, n in sorted(counts.items())) or "nothing to do"
        core_logger.print_to_log(
            f"Eight Sleep sync ({label}) {window_start}..{window_end}: {len(days)} days fetched; {summary}"
        )
    except Exception as err:
        core_logger.print_to_log(f"Eight Sleep sync ({label}) failed: {type(err).__name__}: {err}", "error")


def sync_recent() -> None:
    """Re-sync the last ``RECENT_DAYS`` days."""
    _run("recent", history=False)


def sync_history() -> None:
    """Re-sync every night Eight Sleep has."""
    _run("history", history=True)


def _has_rows() -> bool:
    # HRV rows, not sleep rows: sleep imported before sleep_hrv existed still
    # needs the full-history run to fill it.
    with SessionLocal() as db:
        return db.execute(select(SleepHrv.date).limit(1)).scalar_one_or_none() is not None


def register_jobs() -> None:
    """Add the jobs to upstream's scheduler. A no-op when Eight Sleep is not configured."""
    if not eight_sleep_client.owns_sleep():
        return
    core_scheduler.add_scheduler_job(sync_recent, "interval", 60, [], "sync Eight Sleep sleep for the last 30 days")
    core_scheduler.add_scheduler_job(sync_history, "interval", 1440, [], "sync the full Eight Sleep sleep history")
    # At startup: the backfill if no HRV has been imported yet, otherwise the
    # recent window, so a deploy never waits an hour for its first sync.
    try:
        startup = sync_recent if _has_rows() else sync_history
    except Exception as err:
        core_logger.print_to_log(f"Eight Sleep sync: startup check failed: {type(err).__name__}", "error")
        startup = sync_recent
    core_scheduler.scheduler.add_job(
        startup,
        "date",
        id="homelab_eight_sleep_startup",
        replace_existing=True,
        misfire_grace_time=None,
    )
