"""Rebuild FIT activities' speed and pace streams from the device's own speed.

Before the fork's importer change (``_handle_record_frame`` in
``activities/activity_file_import/utils_fit.py``), FIT imports derived speed
from the distance between consecutive 1 s GPS fixes, so the stored speed (5)
and pace (6) streams are dominated by GPS position error. This re-reads each
activity's stored ``<id>.fit`` with the current importer and rewrites those two
streams. It changes data only (no schema), and only existing stream rows of
activities whose file records a device speed.

Run inside the backend container, from ``/app/backend``::

    python -m homelab.fit_speed_backfill                 # dry run: report only
    python -m homelab.fit_speed_backfill --apply
    python -m homelab.fit_speed_backfill --apply --activity-id 2444
"""

import argparse
import os
import pathlib
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from importlib import import_module

import fitdecode
from sqlalchemy import select
from sqlalchemy.orm import Session

import activities.activity.models as activities_models
import activities.activity_file_import.utils as file_import_utils
import activities.activity_file_import.utils_fit as utils_fit
import activities.activity_streams.constants as streams_constants
import activities.activity_streams.models as streams_models

SPEED = streams_constants.STREAM_TYPE_SPEED
PACE = streams_constants.STREAM_TYPE_PACE

_STREAM_KEYS = {SPEED: "vel_waypoints", PACE: "pace_waypoints"}


@dataclass
class FitSpeedStreams:
    """Speed and pace waypoints for a whole FIT file, as the importer builds them."""

    vel_waypoints: list[dict]
    pace_waypoints: list[dict]
    has_device_speed: bool


def _has_device_speed(frame) -> bool:
    return (
        utils_fit.get_value_from_frame(frame, "enhanced_speed") is not None
        or utils_fit.get_value_from_frame(frame, "speed") is not None
    )


def streams_from_frames(frames: Iterable) -> FitSpeedStreams:
    """
    Run a FIT file's records through the importer's record handler.

    Only record messages are parsed: the importer's session handler geocodes
    each session's start over the network, which a backfill must not repeat.
    A session message still resets the GPS cursor, as it does on import.

    Args:
        frames: FIT data messages in file order.

    Returns:
        The speed and pace waypoints, and whether any record carried a device
        speed (without one the importer falls back to GPS and nothing changes).
    """
    state = utils_fit.FitParseState()
    has_device_speed = False
    for frame in frames:
        if frame.name == "session":
            state.reset_record_cursor()
        elif frame.name == "record":
            has_device_speed = has_device_speed or _has_device_speed(frame)
            utils_fit._handle_record_frame(frame, state)
    return FitSpeedStreams(state.vel_waypoints, state.pace_waypoints, has_device_speed)


def read_fit_file(path: str) -> FitSpeedStreams:
    """
    Parse a FIT file's speed and pace waypoints.

    Args:
        path: Path to the ``.fit`` file.

    Returns:
        The file's speed and pace streams.
    """
    with open(path, "rb") as fit_file:
        frames = (frame for frame in fitdecode.FitReader(fit_file) if isinstance(frame, fitdecode.FitDataMessage))
        return streams_from_frames(frames)


def rebuild_activity_streams(
    db: Session,
    activity: activities_models.Activity,
    parsed: FitSpeedStreams,
) -> str:
    """
    Replace an activity's speed and pace stream waypoints with ``parsed``.

    The file's waypoints are cut to the activity's start/end, as the importer
    cuts each session. The caller commits.

    Args:
        db: Database session.
        activity: The activity whose streams to rewrite.
        parsed: The activity file's parsed streams.

    Returns:
        ``updated``, ``no_device_speed`` or ``no_samples``.
    """
    if not parsed.has_device_speed:
        return "no_device_speed"
    cut = file_import_utils.filter_streams_by_time_range(
        {"vel_waypoints": parsed.vel_waypoints, "pace_waypoints": parsed.pace_waypoints},
        activity.start_time,
        activity.end_time,
    )
    if not cut["vel_waypoints"]:
        return "no_samples"
    rows = db.scalars(
        select(streams_models.ActivityStreams).where(
            streams_models.ActivityStreams.activity_id == activity.id,
            streams_models.ActivityStreams.stream_type.in_(_STREAM_KEYS),
        )
    ).all()
    for row in rows:
        row.stream_waypoints = cut[_STREAM_KEYS[row.stream_type]]
    return "updated"


def _candidates(db: Session, activity_id: int | None) -> list[activities_models.Activity]:
    stmt = (
        select(activities_models.Activity)
        .where(
            activities_models.Activity.id.in_(
                select(streams_models.ActivityStreams.activity_id).where(
                    streams_models.ActivityStreams.stream_type.in_(_STREAM_KEYS)
                )
            )
        )
        .order_by(activities_models.Activity.id)
    )
    if activity_id is not None:
        stmt = stmt.where(activities_models.Activity.id == activity_id)
    return list(db.scalars(stmt).all())


def run(db: Session, files_dir: str, apply: bool, activity_id: int | None = None) -> Counter:
    """
    Rebuild the speed and pace streams of every activity with a stored FIT file.

    Args:
        db: Database session.
        files_dir: Directory holding the processed ``<id>.fit`` files.
        apply: Commit the changes; otherwise roll them back (dry run).
        activity_id: Limit the run to one activity.

    Returns:
        How many activities ended in each outcome.
    """
    outcomes: Counter = Counter()
    for activity in _candidates(db, activity_id):
        path = os.path.join(files_dir, f"{activity.id}.fit")
        if not os.path.exists(path):
            outcomes["not_fit"] += 1
            continue
        try:
            outcome = rebuild_activity_streams(db, activity, read_fit_file(path))
        except Exception as err:  # one bad file must not stop the run
            print(f"activity {activity.id}: {err}")  # noqa: T201 - CLI output
            outcome = "error"
        outcomes[outcome] += 1
        if apply:
            db.commit()
        else:
            db.rollback()
    return outcomes


def _import_all_models() -> None:
    # Relationships name their targets as strings, so a real query needs every
    # model imported (as alembic/env.py does).
    app_dir = pathlib.Path(__file__).resolve().parents[1]
    for path in sorted(app_dir.glob("**/models.py")):
        import_module(".".join(path.relative_to(app_dir).with_suffix("").parts))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="write the changes (default: dry run)")
    parser.add_argument("--activity-id", type=int, help="only this activity")
    args = parser.parse_args()

    import core.config as core_config
    from core.database import SessionLocal

    _import_all_models()
    with SessionLocal() as db:
        outcomes = run(db, core_config.FILES_PROCESSED_DIR, args.apply, args.activity_id)
    mode = "applied" if args.apply else "dry run"
    summary = ", ".join(f"{key} {count}" for key, count in sorted(outcomes.items()))
    print(f"{mode}: {summary}")  # noqa: T201 - CLI output


if __name__ == "__main__":
    main()
