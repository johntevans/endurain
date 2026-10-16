"""Homelab fork: FIT speed from the device, and the backfill that applies it to old imports."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

import activities.activity_file_import.utils_fit as utils_fit
import activities.activity_streams.models as streams_models
from homelab import fit_speed_backfill
from tests._helpers.db import create_sqlite_session
from tests.homelab.test_training_log import _activity

START = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)
# 1e-5 degrees of latitude ≈ 1.11 m; in FIT semicircles that is 1e-5 * 2**31 / 180.
SEMICIRCLES_PER_DEGREE = 2**31 / 180


class _Frame:
    """Minimal stand-in for a fitdecode data message."""

    def __init__(self, name: str, **values):
        self.name = name
        self._values = values

    def get_value(self, key, default=None):
        if key not in self._values:
            raise KeyError(key)
        return self._values[key]


def _record(second: int, lat_offset: float, **speed) -> _Frame:
    return _Frame(
        "record",
        timestamp=START + timedelta(seconds=second),
        position_lat=round((45.0 + lat_offset) * SEMICIRCLES_PER_DEGREE),
        position_long=round(-122.0 * SEMICIRCLES_PER_DEGREE),
        **speed,
    )


def _parse(frames) -> utils_fit.FitParseState:
    state = utils_fit.FitParseState()
    for frame in frames:
        utils_fit._dispatch_data_message(frame, state, None)
    return state


class TestRecordSpeed:
    def test_prefers_the_device_speed_over_gps(self):
        # GPS says ~11 m/s between the fixes; the watch says 2.8 m/s.
        state = _parse([_record(0, 0, enhanced_speed=2.8), _record(1, 1e-4, enhanced_speed=2.8)])
        assert [w["vel"] for w in state.vel_waypoints] == [2.8, 2.8]
        assert state.pace_waypoints[0]["pace"] == pytest.approx(1 / 2.8)
        assert state.is_velocity_set

    def test_uses_legacy_speed_without_enhanced_speed(self):
        state = _parse([_record(0, 0, speed=3.0)])
        assert state.vel_waypoints == [{"time": "2026-10-16T12:00:00", "vel": 3.0}]

    def test_falls_back_to_gps_without_a_speed_field(self):
        state = _parse([_record(0, 0), _record(1, 1e-5)])
        # First fix has no previous one; the second is ~1.11 m in 1 s.
        assert len(state.vel_waypoints) == 1
        assert state.vel_waypoints[0]["vel"] == pytest.approx(1.11, abs=0.01)

    def test_indoor_records_get_a_speed_without_gps(self):
        frame = _Frame("record", timestamp=START, enhanced_speed=2.5)
        state = _parse([frame])
        assert state.vel_waypoints == [{"time": "2026-10-16T12:00:00", "vel": 2.5}]


class TestStreamsFromFrames:
    def test_flags_files_with_a_device_speed(self):
        parsed = fit_speed_backfill.streams_from_frames([_record(0, 0, enhanced_speed=2.8)])
        assert parsed.has_device_speed
        assert parsed.vel_waypoints[0]["vel"] == 2.8

    def test_does_not_geocode_sessions(self, monkeypatch):
        def fail(*args):
            raise AssertionError("geocoded")

        monkeypatch.setattr(utils_fit.activity_file_import_utils, "resolve_location", fail)
        session = _Frame("session", start_position_lat=1, start_position_long=1)
        parsed = fit_speed_backfill.streams_from_frames([_record(0, 0, enhanced_speed=2.8), session])
        assert parsed.vel_waypoints[0]["vel"] == 2.8

    def test_flags_gps_only_files(self):
        parsed = fit_speed_backfill.streams_from_frames([_record(0, 0), _record(1, 1e-5)])
        assert not parsed.has_device_speed


@pytest.fixture
def db() -> Iterator[Session]:
    session = create_sqlite_session()
    try:
        yield session
    finally:
        session.close()
        session.bind.dispose()


def _stream(activity_id: int, stream_type: int, waypoints: list[dict]) -> streams_models.ActivityStreams:
    return streams_models.ActivityStreams(activity_id=activity_id, stream_type=stream_type, stream_waypoints=waypoints)


def _waypoints(db: Session, activity_id: int, stream_type: int) -> list[dict]:
    return db.scalars(
        select(streams_models.ActivityStreams.stream_waypoints).where(
            streams_models.ActivityStreams.activity_id == activity_id,
            streams_models.ActivityStreams.stream_type == stream_type,
        )
    ).one()


def _parsed(speeds: list[float], has_device_speed: bool = True) -> fit_speed_backfill.FitSpeedStreams:
    times = [(START + timedelta(seconds=i)).strftime("%Y-%m-%dT%H:%M:%S") for i in range(len(speeds))]
    return fit_speed_backfill.FitSpeedStreams(
        vel_waypoints=[{"time": t, "vel": v} for t, v in zip(times, speeds, strict=True)],
        pace_waypoints=[{"time": t, "pace": 1 / v} for t, v in zip(times, speeds, strict=True)],
        has_device_speed=has_device_speed,
    )


class TestRebuildActivityStreams:
    def _seed(self, db: Session) -> None:
        activity = _activity(1, START + timedelta(seconds=1), end_time=START + timedelta(seconds=2))
        old = [{"time": "2026-10-16T12:00:01", "vel": 9.9}]
        db.add_all(
            [
                activity,
                _stream(1, fit_speed_backfill.SPEED, old),
                _stream(1, fit_speed_backfill.PACE, [{"time": "2026-10-16T12:00:01", "pace": 0.1}]),
                _stream(1, 1, [{"time": "2026-10-16T12:00:01", "hr": 140}]),
            ]
        )
        db.commit()

    def test_rewrites_speed_and_pace_within_the_activity(self, db):
        self._seed(db)
        activity = db.get(_activity(1, START).__class__, 1)
        outcome = fit_speed_backfill.rebuild_activity_streams(db, activity, _parsed([2.0, 2.5, 3.0, 3.5]))
        db.commit()
        assert outcome == "updated"
        # Seconds 1 and 2 of the file fall inside the activity.
        assert [w["vel"] for w in _waypoints(db, 1, fit_speed_backfill.SPEED)] == [2.5, 3.0]
        assert [w["pace"] for w in _waypoints(db, 1, fit_speed_backfill.PACE)] == [1 / 2.5, 1 / 3.0]
        assert _waypoints(db, 1, 1) == [{"time": "2026-10-16T12:00:01", "hr": 140}]

    def test_leaves_gps_only_files_alone(self, db):
        self._seed(db)
        activity = db.get(_activity(1, START).__class__, 1)
        outcome = fit_speed_backfill.rebuild_activity_streams(db, activity, _parsed([2.0], has_device_speed=False))
        assert outcome == "no_device_speed"
        assert _waypoints(db, 1, fit_speed_backfill.SPEED) == [{"time": "2026-10-16T12:00:01", "vel": 9.9}]

    def test_leaves_streams_alone_when_no_sample_falls_inside(self, db):
        self._seed(db)
        activity = db.get(_activity(1, START).__class__, 1)
        late = fit_speed_backfill.FitSpeedStreams(
            vel_waypoints=[{"time": "2026-10-16T13:00:00", "vel": 2.0}],
            pace_waypoints=[{"time": "2026-10-16T13:00:00", "pace": 0.5}],
            has_device_speed=True,
        )
        assert fit_speed_backfill.rebuild_activity_streams(db, activity, late) == "no_samples"
        assert _waypoints(db, 1, fit_speed_backfill.SPEED) == [{"time": "2026-10-16T12:00:01", "vel": 9.9}]

    def test_run_skips_activities_without_a_fit_file_and_dry_runs(self, db, tmp_path, monkeypatch):
        self._seed(db)
        assert fit_speed_backfill.run(db, str(tmp_path), apply=True) == {"not_fit": 1}

        (tmp_path / "1.fit").write_bytes(b"")
        monkeypatch.setattr(fit_speed_backfill, "read_fit_file", lambda path: _parsed([2.0, 2.5, 3.0]))
        assert fit_speed_backfill.run(db, str(tmp_path), apply=False) == {"updated": 1}
        assert _waypoints(db, 1, fit_speed_backfill.SPEED) == [{"time": "2026-10-16T12:00:01", "vel": 9.9}]

        assert fit_speed_backfill.run(db, str(tmp_path), apply=True, activity_id=1) == {"updated": 1}
        assert [w["vel"] for w in _waypoints(db, 1, fit_speed_backfill.SPEED)] == [2.5, 3.0]
