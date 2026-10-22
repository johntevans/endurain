"""Homelab fork: Intervals.icu-style training load (calculator, cache, CLI, routes).

The calculator tests use synthetic streams whose loads can be worked out by
hand. The cache and backfill run against in-memory SQLite with the
``homelab`` schema attached, as in ``test_activity_tags.py``.
"""

import argparse
import dataclasses
import math
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

import activities.activity.models as activities_models
import activities.activity_streams.models as streams_models
from homelab.database import HomelabBase
from homelab.training_load import calculate, cli
from homelab.training_load import crud as load_crud
from homelab.training_load.calculate import LoadSource, Thresholds
from homelab.training_load.models import ActivityLoad, TrainingLoadSettings
from homelab.training_load.schema import ActivityLoadRead
from homelab.training_log import crud as training_log_crud
from tests._helpers.db import create_sqlite_session
from tests.homelab.test_training_log import OTHER, OWNER, _activity

# The owner's Intervals.icu settings: 43 / 159 / 175 bpm, 7:00/mi.
ATHLETE = Thresholds(resting_hr=43, threshold_hr=159, max_hr=175, threshold_speed=1609.344 / 420)
START = datetime(2026, 10, 12, 12, tzinfo=UTC)
T0 = datetime(2026, 10, 12, 12)


def _stream(key: str, values, step_s: float = 1.0, iso: bool = True) -> list[dict]:
    """Waypoints one ``step_s`` apart, timed like a file import (ISO) or Strava (offsets)."""
    points = []
    for index, value in enumerate(values):
        offset = index * step_s
        when = (T0 + timedelta(seconds=offset)).strftime("%Y-%m-%dT%H:%M:%S") if iso else int(offset)
        points.append({"time": when, key: value})
    return points


def _trimp(reserve: float, a: float = 0.64, b: float = 1.92) -> float:
    return reserve * a * math.exp(b * reserve)


class TestHrLoad:
    def test_one_hour_at_threshold_is_100(self):
        assert calculate.hr_load(_stream("hr", [159] * 3601), ATHLETE) == pytest.approx(100)

    def test_matches_hand_computed_hrss(self):
        # 30 minutes at 130 bpm: (30 * w(87/132)) / (60 * w(116/132)) * 100.
        expected = 30 * _trimp(87 / 132) / (60 * _trimp(116 / 132)) * 100
        assert calculate.hr_load(_stream("hr", [130] * 1801), ATHLETE) == pytest.approx(expected)

    def test_sums_per_sample_not_from_the_average(self):
        # Half at 120, half at 158: average 139, but TRIMP is convex, so more.
        mixed = calculate.hr_load(_stream("hr", [120] * 1800 + [158] * 1801), ATHLETE)
        steady = calculate.hr_load(_stream("hr", [139] * 3601), ATHLETE)
        assert mixed > steady

    def test_clamps_to_resting_and_max(self):
        assert calculate.hr_load(_stream("hr", [30] * 601), ATHLETE) == 0
        assert calculate.hr_load(_stream("hr", [200] * 3601), ATHLETE) == pytest.approx(
            100 * _trimp(1.0) / _trimp(116 / 132)
        )

    def test_a_long_gap_is_a_pause(self):
        points = _stream("hr", [159] * 1801)
        later = [
            {"time": (T0 + timedelta(seconds=7200 + i)).strftime("%Y-%m-%dT%H:%M:%S"), "hr": 159} for i in range(1801)
        ]
        assert calculate.hr_load(points + later, ATHLETE) == pytest.approx(100)

    def test_strava_offsets_and_unsorted_samples(self):
        points = _stream("hr", [159] * 3601, iso=False)
        assert calculate.hr_load(list(reversed(points)), ATHLETE) == pytest.approx(100)

    def test_female_constants(self):
        athlete = dataclasses.replace(ATHLETE, gender="female")
        expected = 30 * _trimp(87 / 132, 0.86, 1.67) / (60 * _trimp(116 / 132, 0.86, 1.67)) * 100
        assert calculate.hr_load(_stream("hr", [130] * 1801), athlete) == pytest.approx(expected)

    @pytest.mark.parametrize("points", [[], [{"time": "2026-10-12T12:00:00", "hr": 150}], [{"hr": 1}, {"hr": 2}]])
    def test_too_few_samples(self, points):
        assert calculate.hr_load(points, ATHLETE) is None


class TestPaceLoad:
    def test_one_hour_at_threshold_pace_is_100(self):
        assert calculate.pace_load(ATHLETE.threshold_speed, 3600, ATHLETE) == pytest.approx(100)

    def test_scales_with_the_square_of_intensity(self):
        assert calculate.pace_load(ATHLETE.threshold_speed * 0.75, 1800, ATHLETE) == pytest.approx(28.125)

    def test_gap_speed_of_a_flat_run_is_its_speed(self):
        assert calculate.gap_speed(_stream("vel", [3.0] * 601), []) == pytest.approx(3.0)

    def test_gap_speed_skips_standing_still(self):
        vel = [3.0] * 300 + [0.0] * 120 + [3.0] * 301
        assert calculate.gap_speed(_stream("vel", vel), []) == pytest.approx(3.0, rel=0.01)

    def test_uphill_counts_as_faster_on_the_flat(self):
        vel = _stream("vel", [3.0] * 601)
        climb = _stream("ele", [i * 3.0 * 0.05 for i in range(601)])  # 5% all the way
        assert calculate.gap_speed(vel, climb) == pytest.approx(3.0 * (1 + 0.02869556 * 5 + 0.001520768 * 25), rel=0.01)

    def test_never_moving(self):
        assert calculate.gap_speed(_stream("vel", [0.2] * 60), []) is None
        assert calculate.pace_load(0, 3600, ATHLETE) is None


class TestActivityLoad:
    def _run_streams(self, seconds: int = 1800, speed: float = 1609.344 / 563) -> dict[str, list[dict]]:
        # 30 min easy at 9:23/mi and 121 bpm, like the owner's 2026-10-16 run (Intervals: 28).
        return {"hr": _stream("hr", [121] * (seconds + 1)), "vel": _stream("vel", [speed] * (seconds + 1))}

    def test_run_uses_pace_with_timer_time(self):
        result = calculate.activity_load(1, 1823, 5211, self._run_streams(), ATHLETE)
        assert result.source is LoadSource.PACE
        assert result.load == 28
        assert result.pace_load == pytest.approx(1823 / 3600 * (420 / 563) ** 2 * 100, rel=0.001)
        assert result.hr_load is not None

    def test_run_without_a_speed_stream_uses_distance_over_timer_time(self):
        result = calculate.activity_load(40, 1980, 5281, {"hr": _stream("hr", [115] * 1981)}, ATHLETE)
        assert result.source is LoadSource.PACE
        speed = 5281 / 1980
        assert result.pace_load == pytest.approx(1980 / 3600 * (speed / ATHLETE.threshold_speed) ** 2 * 100)

    def test_run_without_pace_falls_back_to_hr(self):
        result = calculate.activity_load(1, 0, 0, {"hr": _stream("hr", [159] * 3601)}, ATHLETE)
        assert (result.source, result.load) == (LoadSource.HR, 100)

    def test_ride_uses_hr_even_with_speed(self):
        result = calculate.activity_load(4, 3600, 30000, self._run_streams(3600, 8.0), ATHLETE)
        assert result.source is LoadSource.HR
        assert result.pace_load is None

    @pytest.mark.parametrize("activity_type", [10, 14, 19, 1001])
    def test_strength_types_have_zero_load_but_keep_hr(self, activity_type):
        result = calculate.activity_load(activity_type, 1900, 0, {"hr": _stream("hr", [99] * 1901)}, ATHLETE)
        assert (result.load, result.source) == (0, LoadSource.NONE)
        assert calculate.round_load(result.hr_load) == 11  # Intervals: (11) on the 2026-10-13 session

    def test_no_data(self):
        assert calculate.activity_load(4, 3600, 0, {}, ATHLETE) == calculate.LoadResult(0, LoadSource.NONE, None, None)

    @pytest.mark.parametrize(("value", "expected"), [(65.5, 66), (84.49, 84), (0.5, 1), (0.0, 0)])
    def test_rounds_half_up(self, value, expected):
        assert calculate.round_load(value) == expected


@pytest.fixture
def db() -> Iterator[Session]:
    """SQLite session with upstream tables plus the attached ``homelab`` schema."""
    session = create_sqlite_session()
    session.execute(text("ATTACH DATABASE ':memory:' AS homelab"))
    HomelabBase.metadata.create_all(session.connection())
    session.commit()
    try:
        yield session
    finally:
        session.close()
        session.bind.dispose()


def _settings(user_id: int = OWNER, updated_at: datetime = START - timedelta(days=30)) -> TrainingLoadSettings:
    return TrainingLoadSettings(
        user_id=user_id,
        resting_hr=43,
        threshold_hr=159,
        max_hr=175,
        threshold_pace=420 * 1000 / 1609.344,
        updated_at=updated_at,
    )


def _hr_streams(activity_id: int, bpm: int = 159, seconds: int = 3600) -> streams_models.ActivityStreams:
    return streams_models.ActivityStreams(
        activity_id=activity_id, stream_type=1, stream_waypoints=_stream("hr", [bpm] * (seconds + 1))
    )


def _ride(activity_id: int, start: datetime = START, **overrides):
    return _activity(activity_id, start, activity_type=4, **overrides)


class TestEnsureLoads:
    def test_computes_and_caches(self, db):
        db.add_all([_settings(), _ride(1), _hr_streams(1)])
        db.commit()

        loads = load_crud.ensure_loads(OWNER, [1], db)

        assert loads[1] == ActivityLoadRead(activity_id=1, load=100, source=LoadSource.HR, pace_load=None, hr_load=100)
        stored = db.get(ActivityLoad, 1)
        assert (stored.load, stored.activity_type) == (100, 4)
        computed_at = stored.computed_at
        load_crud.ensure_loads(OWNER, [1], db)
        db.refresh(stored)
        assert stored.computed_at == computed_at

    def test_without_settings_nothing(self, db):
        db.add_all([_ride(1), _hr_streams(1)])
        db.commit()
        assert load_crud.ensure_loads(OWNER, [1], db) == {}
        assert db.scalars(select(ActivityLoad)).all() == []

    def test_only_the_users_own_activities_from_the_start_date(self, db):
        db.add_all(
            [
                _settings(),
                _ride(1),
                _ride(2, user_id=OTHER),
                _ride(3, load_crud.LOAD_START - timedelta(seconds=1)),
                _ride(4, load_crud.LOAD_START),
            ]
        )
        db.commit()
        assert set(load_crud.ensure_loads(OWNER, [1, 2, 3, 4], db)) == {1, 4}

    def test_recomputes_after_a_settings_change(self, db):
        settings = _settings()
        db.add_all([settings, _ride(1), _hr_streams(1, bpm=130)])
        db.commit()
        before = load_crud.ensure_loads(OWNER, [1], db)[1].load

        settings.threshold_hr = 150
        settings.updated_at = datetime.now(UTC) + timedelta(seconds=1)
        db.commit()

        assert load_crud.ensure_loads(OWNER, [1], db)[1].load > before

    def test_recomputes_after_a_type_change(self, db):
        db.add_all([_settings(), _ride(1), _hr_streams(1, bpm=99)])
        db.commit()
        assert load_crud.ensure_loads(OWNER, [1], db)[1].source is LoadSource.HR

        activity = db.get(activities_models.Activity, 1)
        activity.activity_type = 19
        db.commit()

        assert load_crud.ensure_loads(OWNER, [1], db)[1].load == 0

    def test_caps_the_work_per_request(self, db):
        db.add(_settings())
        db.add_all([_ride(i, START + timedelta(minutes=i)) for i in range(1, 6)])
        db.commit()
        with patch.object(load_crud, "MAX_COMPUTED_PER_REQUEST", 2):
            assert len(load_crud.ensure_loads(OWNER, range(1, 6), db)) == 2
            assert len(load_crud.ensure_loads(OWNER, range(1, 6), db)) == 4

    def test_a_database_error_returns_what_is_stored(self):
        from sqlalchemy.exc import SQLAlchemyError

        session = MagicMock(spec=Session)
        session.get.side_effect = SQLAlchemyError("boom")
        session.scalars.side_effect = SQLAlchemyError("still down")
        assert load_crud.ensure_loads(OWNER, [1], session) == {}
        session.rollback.assert_called_once()


class TestGetActivityLoad:
    def test_owner_gets_the_load(self, db):
        db.add_all([_settings(), _ride(1), _hr_streams(1)])
        db.commit()
        assert load_crud.get_activity_load(1, OWNER, db).load == 100

    def test_empty_without_a_load(self, db):
        db.add(_ride(1))
        db.commit()
        assert load_crud.get_activity_load(1, OWNER, db) == ActivityLoadRead(activity_id=1)

    @pytest.mark.parametrize("activity_id", [1, 99])
    def test_404_for_anyone_else_or_a_missing_activity(self, db, activity_id):
        db.add_all([_settings(OTHER), _ride(1, user_id=OTHER)])
        db.commit()
        with pytest.raises(HTTPException) as exc:
            load_crud.get_activity_load(activity_id, OWNER, db)
        assert exc.value.status_code == 404


class TestTrainingLog:
    def test_activities_carry_their_load(self, db):
        db.add_all([_settings(), _ride(1), _hr_streams(1), _ride(2, load_crud.LOAD_START - timedelta(days=1))])
        db.commit()

        result = training_log_crud.get_training_log_activities(OWNER, date(2025, 12, 1), date(2026, 10, 18), db)

        assert {item.id: item.load for item in result} == {2: None, 1: 100}


class TestCli:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [("7:00/mi", 420 * 1000 / 1609.344), ("4:21/km", 261.0), ("7:00 / mi", 420 * 1000 / 1609.344)],
    )
    def test_parse_pace(self, value, expected):
        assert cli.parse_pace(value) == pytest.approx(expected)

    @pytest.mark.parametrize("value", ["7", "7:60/mi", "0:00/km", "7:00/yd"])
    def test_parse_pace_rejects(self, value):
        with pytest.raises(argparse.ArgumentTypeError):
            cli.parse_pace(value)

    def test_set_settings_creates_then_replaces(self, db):
        cli.set_settings(db, OWNER, 43, 159, 175, 260.97)
        row = cli.set_settings(db, OWNER, 45, 160, 176, 255.0)
        assert (row.resting_hr, row.threshold_hr, row.max_hr, row.threshold_pace) == (45, 160, 176, 255.0)
        assert len(db.scalars(select(TrainingLoadSettings)).all()) == 1

    def test_backfill_dry_run_writes_nothing(self, db):
        db.add_all([_settings(), _ride(1), _hr_streams(1), _ride(2, user_id=OTHER)])
        db.commit()

        outcomes, computed = cli.backfill(db, apply=False, since=load_crud.LOAD_START)

        assert outcomes == {"hr": 1, "no_settings": 1}
        assert [(activity.id, row.load) for activity, row in computed] == [(1, 100)]
        assert db.scalars(select(ActivityLoad)).all() == []

    def test_backfill_apply_writes_and_reruns_in_place(self, db):
        db.add_all([_settings(), _ride(1), _hr_streams(1), _ride(2, START + timedelta(days=1))])
        db.commit()

        cli.backfill(db, apply=True, since=load_crud.LOAD_START)
        outcomes, _ = cli.backfill(db, apply=True, since=load_crud.LOAD_START, activity_id=2)

        assert outcomes == {"none": 1}
        assert {row.activity_id: row.source for row in db.scalars(select(ActivityLoad))} == {1: "hr", 2: "none"}

    def test_backfill_refuses_dates_before_the_start(self):
        assert cli.main(["backfill", "--since", "2025-12-31"]) == 2


def _build_app(mock_db, user_id: int = OWNER) -> FastAPI:
    import auth.dependencies as auth_deps
    import core.database as core_db
    from homelab.training_load import router

    app = FastAPI()
    app.include_router(router.router, prefix="/homelab/training_load")
    app.dependency_overrides[auth_deps.check_scopes] = lambda: None
    app.dependency_overrides[auth_deps.get_sub_from_access_token] = lambda: user_id
    app.dependency_overrides[core_db.get_db] = lambda: mock_db
    return app


class TestRoutes:
    @patch("homelab.training_load.crud.get_activity_load")
    def test_get_passes_activity_and_token_user(self, mock_get):
        mock_db = MagicMock(spec=Session)
        mock_get.return_value = ActivityLoadRead(
            activity_id=3, load=74, source=LoadSource.PACE, pace_load=74, hr_load=48
        )
        resp = TestClient(_build_app(mock_db, user_id=7)).get("/homelab/training_load?activity_id=3")
        assert resp.status_code == 200
        assert resp.json() == {"activity_id": 3, "load": 74, "source": "pace", "pace_load": 74, "hr_load": 48}
        mock_get.assert_called_once_with(3, 7, mock_db)

    @pytest.mark.parametrize("query", ["", "?activity_id=0", "?activity_id=x"])
    def test_get_validates_the_activity_id(self, query):
        app = _build_app(MagicMock(spec=Session))
        assert TestClient(app).get(f"/homelab/training_load{query}").status_code == 422

    def test_route_is_registered_in_the_api_router(self):
        from core.routes import router as api_router

        app = FastAPI()
        app.include_router(api_router)
        assert set(app.openapi()["paths"]["/api/v1/homelab/training_load"]) == {"get"}


def test_decimal_timer_time_is_accepted(db):
    db.add_all([_settings(), _activity(1, START, total_timer_time=Decimal("1823.5")), _hr_streams(1, seconds=60)])
    db.commit()
    assert load_crud.ensure_loads(OWNER, [1], db)[1].source is LoadSource.PACE
