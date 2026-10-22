"""Set training-load thresholds and backfill activity loads.

In the backend container, from ``/app/backend``::

    python -m homelab.training_load.cli settings --user-id 1 \\
        --resting-hr 43 --threshold-hr 159 --max-hr 175 --threshold-pace 7:00/mi
    python -m homelab.training_load.cli backfill            # dry run: counts and a sample
    python -m homelab.training_load.cli backfill --apply [--user-id N] [--activity-id N] [--since 2026-01-01]

The backfill reads the streams already in the database (FIT, GPX, TCX and
Strava imports alike) and only writes ``homelab.activity_loads``; undo is
``DELETE FROM homelab.activity_loads``. Changing the settings makes every
load stale: run the backfill again (readers would otherwise recompute them a
few at a time).
"""

import argparse
import pathlib
import re
import sys
from collections import Counter
from datetime import UTC, date, datetime, time
from importlib import import_module

from sqlalchemy import select
from sqlalchemy.orm import Session

import activities.activity.models as activities_models
from homelab.training_load import crud as load_crud
from homelab.training_load.models import ActivityLoad, TrainingLoadSettings

Activity = activities_models.Activity

# Activities per batch: their streams are held in memory together.
_BATCH = 25

_METRES_PER_MILE = 1609.344


def parse_pace(value: str) -> float:
    """
    Parse a pace like ``7:00/mi`` or ``4:21/km`` into seconds per kilometre.

    Raises:
        argparse.ArgumentTypeError: For anything else.
    """
    match = re.fullmatch(r"(\d+):([0-5]\d)\s*/\s*(mi|km)", value.strip())
    if not match:
        raise argparse.ArgumentTypeError(f"expected a pace like 7:00/mi or 4:21/km, got {value!r}")
    seconds = int(match[1]) * 60 + int(match[2])
    if seconds <= 0:
        raise argparse.ArgumentTypeError("pace must be positive")
    return seconds * 1000 / _METRES_PER_MILE if match[3] == "mi" else float(seconds)


def set_settings(
    db: Session,
    user_id: int,
    resting_hr: int,
    threshold_hr: int,
    max_hr: int,
    threshold_pace: float,
) -> TrainingLoadSettings:
    """Create or replace a user's thresholds (committed). Every existing load becomes stale."""
    row = db.get(TrainingLoadSettings, user_id)
    if row is None:
        row = TrainingLoadSettings(user_id=user_id)
        db.add(row)
    row.resting_hr = resting_hr
    row.threshold_hr = threshold_hr
    row.max_hr = max_hr
    row.threshold_pace = threshold_pace
    row.updated_at = datetime.now(UTC)
    db.commit()
    return row


def backfill(
    db: Session,
    apply: bool,
    since: datetime,
    user_id: int | None = None,
    activity_id: int | None = None,
) -> tuple[Counter, list[tuple[Activity, ActivityLoad]]]:
    """
    Compute the load of every activity from ``since`` on, for users with settings.

    Args:
        db: Database session.
        apply: Commit the rows; otherwise roll them back (dry run).
        since: Earliest start time (not before ``crud.LOAD_START``).
        user_id: Only this user's activities.
        activity_id: Only this activity.

    Returns:
        Counts by load source (and ``no_settings``), and every activity with
        its computed row, oldest first.
    """
    outcomes: Counter = Counter()
    computed: list[tuple[Activity, ActivityLoad]] = []
    stmt = select(Activity).where(Activity.start_time >= since).order_by(Activity.start_time, Activity.id)
    if user_id is not None:
        stmt = stmt.where(Activity.user_id == user_id)
    if activity_id is not None:
        stmt = stmt.where(Activity.id == activity_id)
    activities = list(db.scalars(stmt).all())

    by_user: dict[int, list[Activity]] = {}
    for activity in activities:
        by_user.setdefault(activity.user_id, []).append(activity)

    for owner_id, owned in by_user.items():
        settings = load_crud.get_settings(owner_id, db)
        if settings is None:
            outcomes["no_settings"] += len(owned)
            continue
        gender = load_crud.user_gender(owner_id, db)
        for start in range(0, len(owned), _BATCH):
            batch = owned[start : start + _BATCH]
            existing = {
                row.activity_id: row
                for row in db.scalars(
                    select(ActivityLoad).where(ActivityLoad.activity_id.in_([a.id for a in batch]))
                ).all()
            }
            rows = load_crud.compute_loads(batch, settings, gender, existing, db)
            for activity in batch:
                row = rows[activity.id]
                outcomes[row.source] += 1
                computed.append((activity, row))
            if apply:
                db.commit()
            else:
                db.flush()
    if not apply:
        db.rollback()
    return outcomes, computed


def _import_all_models() -> None:
    # Relationships name their targets as strings, so a real query needs every
    # model imported (as alembic/env.py does).
    app_dir = pathlib.Path(__file__).resolve().parents[2]
    for path in sorted(app_dir.glob("**/models.py")):
        import_module(".".join(path.relative_to(app_dir).with_suffix("").parts))


def _print_sample(computed: list[tuple[Activity, ActivityLoad]], count: int) -> None:
    for activity, row in computed[-count:]:
        hr = f"{row.hr_load:.1f}" if row.hr_load is not None else "-"
        pace = f"{row.pace_load:.1f}" if row.pace_load is not None else "-"
        print(  # noqa: T201 - CLI output
            f"  {activity.id:>6}  {activity.start_time:%Y-%m-%d}  load {row.load:>4} ({row.source:<4})"
            f"  pace {pace:>6}  hr {hr:>6}  {activity.name or ''}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    settings = sub.add_parser("settings", help="set a user's thresholds")
    settings.add_argument("--user-id", type=int, required=True)
    settings.add_argument("--resting-hr", type=int, required=True)
    settings.add_argument("--threshold-hr", type=int, required=True)
    settings.add_argument("--max-hr", type=int, required=True)
    settings.add_argument("--threshold-pace", type=parse_pace, required=True, help="e.g. 7:00/mi or 4:21/km")

    fill = sub.add_parser("backfill", help="compute activity loads (dry run unless --apply)")
    fill.add_argument("--apply", action="store_true", help="write the loads (default: dry run)")
    fill.add_argument(
        "--since",
        type=date.fromisoformat,
        default=load_crud.LOAD_START.date(),
        help=f"first date, UTC (default and earliest: {load_crud.LOAD_START.date()})",
    )
    fill.add_argument("--user-id", type=int, help="only this user")
    fill.add_argument("--activity-id", type=int, help="only this activity")
    fill.add_argument("--sample", type=int, default=15, help="print the last N activities (default 15)")

    args = parser.parse_args(argv)
    since = datetime.combine(args.since, time.min, tzinfo=UTC) if args.command == "backfill" else None
    if since is not None and since < load_crud.LOAD_START:
        print(  # noqa: T201 - CLI output
            f"--since may not be before {load_crud.LOAD_START.date()}: readers ignore older loads. "
            "Move crud.LOAD_START first.",
            file=sys.stderr,
        )
        return 2

    from core.database import SessionLocal

    _import_all_models()
    with SessionLocal() as db:
        if args.command == "settings":
            row = set_settings(db, args.user_id, args.resting_hr, args.threshold_hr, args.max_hr, args.threshold_pace)
            print(  # noqa: T201 - CLI output
                f"user {row.user_id}: resting {row.resting_hr}, threshold {row.threshold_hr}, max {row.max_hr} bpm; "
                f"threshold pace {row.threshold_pace:.1f} s/km. Run `backfill --apply` to recompute."
            )
            return 0
        outcomes, computed = backfill(db, args.apply, since, args.user_id, args.activity_id)
        _print_sample(computed, args.sample)
    mode = "applied" if args.apply else "dry run"
    summary = ", ".join(f"{key} {count}" for key, count in sorted(outcomes.items())) or "nothing to do"
    print(f"{mode}: {summary}")  # noqa: T201 - CLI output
    return 0


if __name__ == "__main__":
    sys.exit(main())
