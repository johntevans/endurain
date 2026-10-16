"""Homelab fork: lap intensity defaults, owner overrides and quality totals.

Runs against in-memory SQLite with the ``homelab`` schema attached, as in
``test_activity_tags.py``.
"""

from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

import activities.activity_laps.models as laps_models
from homelab.activity_tags.models import ActivityTag
from homelab.database import HomelabBase
from homelab.lap_intensity import crud as intensity_crud
from homelab.lap_intensity.models import LapIntensityOverride
from homelab.lap_intensity.schema import (
    LapIntensityKey,
    LapIntensityRead,
    LapIntensitySource,
    effective_intensity,
)
from homelab.training_log import crud as training_log_crud
from tests._helpers.db import create_sqlite_session
from tests.homelab.test_training_log import OTHER, OWNER, _activity

START = datetime(2026, 10, 13, 7, tzinfo=UTC)


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


def _lap(lap_id: int, activity_id: int, intensity: str | None, minutes: float, metres: float, **overrides):
    fields = {
        "id": lap_id,
        "activity_id": activity_id,
        "start_time": START + timedelta(minutes=lap_id),
        "intensity": intensity,
        "total_timer_time": Decimal(str(minutes * 60)),
        "total_elapsed_time": Decimal(str(minutes * 60 + 5)),
        "total_distance": Decimal(str(metres)),
        **overrides,
    }
    return laps_models.ActivityLaps(**fields)


def _seed(db: Session, *items) -> None:
    db.add_all(items)
    db.commit()


class TestEffectiveIntensity:
    @pytest.mark.parametrize(
        ("override", "recorded", "expected"),
        [
            ("rest", "active", ("rest", LapIntensitySource.OVERRIDE)),
            (None, "warmup", ("warmup", LapIntensitySource.RECORDED)),
            (None, None, ("active", LapIntensitySource.DEFAULT)),
            (None, "", ("active", LapIntensitySource.DEFAULT)),
        ],
    )
    def test_override_then_recorded_then_default(self, override, recorded, expected):
        assert effective_intensity(override, recorded) == expected


class TestGetActivityLapIntensities:
    def test_lists_laps_in_order_with_their_source(self, db):
        _seed(db, _activity(1, START))
        _seed(
            db,
            _lap(12, 1, None, 10, 2000),
            _lap(11, 1, "warmup", 15, 2500),
            _lap(13, 1, "interval", 5, 1000),
            LapIntensityOverride(lap_id=13, intensity="cooldown"),
        )

        result = intensity_crud.get_activity_lap_intensities(1, OWNER, db)

        assert result == [
            LapIntensityRead(lap_id=11, intensity="warmup", recorded="warmup", source=LapIntensitySource.RECORDED),
            LapIntensityRead(lap_id=12, intensity="active", recorded=None, source=LapIntensitySource.DEFAULT),
            LapIntensityRead(lap_id=13, intensity="cooldown", recorded="interval", source=LapIntensitySource.OVERRIDE),
        ]

    def test_someone_elses_activity_is_a_404(self, db):
        _seed(db, _activity(1, START, user_id=OTHER))
        _seed(db, _lap(11, 1, None, 10, 2000))
        with pytest.raises(HTTPException) as err:
            intensity_crud.get_activity_lap_intensities(1, OWNER, db)
        assert err.value.status_code == 404

    def test_database_error_is_a_500(self):
        broken = MagicMock()
        broken.execute.side_effect = SQLAlchemyError("boom")
        with pytest.raises(HTTPException) as err:
            intensity_crud.get_activity_lap_intensities(1, OWNER, broken)
        assert err.value.status_code == 500


class TestSetLapIntensity:
    def test_sets_changes_and_clears_an_override(self, db):
        _seed(db, _activity(1, START))
        _seed(db, _lap(11, 1, "interval", 10, 2000))

        first = intensity_crud.set_lap_intensity(11, LapIntensityKey.WARMUP, OWNER, db)
        assert first == LapIntensityRead(
            lap_id=11, intensity="warmup", recorded="interval", source=LapIntensitySource.OVERRIDE
        )
        intensity_crud.set_lap_intensity(11, LapIntensityKey.COOLDOWN, OWNER, db)
        assert db.execute(select(LapIntensityOverride.intensity)).scalars().all() == ["cooldown"]

        cleared = intensity_crud.set_lap_intensity(11, None, OWNER, db)
        assert cleared.source == LapIntensitySource.RECORDED
        assert cleared.intensity == "interval"
        assert db.execute(select(LapIntensityOverride)).scalars().all() == []

    def test_never_writes_the_upstream_lap(self, db):
        _seed(db, _activity(1, START))
        _seed(db, _lap(11, 1, None, 10, 2000))

        intensity_crud.set_lap_intensity(11, LapIntensityKey.REST, OWNER, db)

        db.expire_all()
        assert db.get(laps_models.ActivityLaps, 11).intensity is None

    @pytest.mark.parametrize("lap_id", [11, 99])
    def test_someone_elses_or_missing_lap_is_a_404(self, db, lap_id):
        _seed(db, _activity(1, START, user_id=OTHER))
        _seed(db, _lap(11, 1, None, 10, 2000))
        with pytest.raises(HTTPException) as err:
            intensity_crud.set_lap_intensity(lap_id, LapIntensityKey.REST, OWNER, db)
        assert err.value.status_code == 404
        assert db.execute(select(LapIntensityOverride)).scalars().all() == []


class TestQualityTotals:
    def test_sums_active_and_interval_laps_after_overrides(self, db):
        _seed(db, _activity(1, START))
        _seed(
            db,
            _lap(11, 1, "warmup", 15, 2500),
            _lap(12, 1, "active", 10, 3000),
            _lap(13, 1, "rest", 2, 200),
            _lap(14, 1, "interval", 10, 2900),
            _lap(15, 1, None, 6, 1500),  # default: active
            _lap(16, 1, "interval", 15, 2400),  # overridden to cooldown
            _lap(17, 1, "active", 1, 300, total_timer_time=None),  # falls back to elapsed time
            LapIntensityOverride(lap_id=16, intensity="cooldown"),
        )

        totals = intensity_crud.get_quality_totals([1], db)

        assert totals[1].timer_time == pytest.approx((10 + 10 + 6) * 60 + 65)
        assert totals[1].distance == pytest.approx(3000 + 2900 + 1500 + 300)

    def test_activities_without_laps_are_left_out(self, db):
        _seed(db, _activity(1, START), _activity(2, START))
        _seed(db, _lap(11, 1, "rest", 2, 200))

        totals = intensity_crud.get_quality_totals([1, 2], db)

        assert set(totals) == {1}
        assert totals[1].timer_time == 0

    def test_no_ids_no_query(self):
        broken = MagicMock()
        assert intensity_crud.get_quality_totals([], broken) == {}
        broken.execute.assert_not_called()


class TestTrainingLogQuality:
    def _log(self, db):
        result = training_log_crud.get_training_log_activities(OWNER, date(2026, 10, 12), date(2026, 10, 18), db)
        return {item.id: (item.quality_time, item.quality_distance) for item in result}

    def test_only_race_workout_and_nsm_sessions_have_quality(self, db):
        _seed(
            db,
            *[_activity(i, START + timedelta(hours=i)) for i in range(1, 7)],
        )
        _seed(
            db,
            *[_lap(10 + i, i, "active", 10, 2000) for i in range(1, 7)],
            ActivityTag(activity_id=1, tag="workout"),
            ActivityTag(activity_id=2, tag="race"),
            ActivityTag(activity_id=3, tag="nsm_medium"),
            ActivityTag(activity_id=4, tag="long_run"),
            ActivityTag(activity_id=5, tag="long_run"),
            ActivityTag(activity_id=5, tag="workout"),
        )

        quality = self._log(db)

        assert quality == {
            1: (600, 2000),
            2: (600, 2000),
            3: (600, 2000),
            4: (0, 0),
            5: (600, 2000),
            6: (0, 0),
        }

    def test_tagged_session_without_laps_counts_whole(self, db):
        _seed(db, _activity(1, START), _activity(2, START, total_timer_time=Decimal("0")))
        _seed(db, ActivityTag(activity_id=1, tag="race"), ActivityTag(activity_id=2, tag="race"))

        assert self._log(db) == {1: (3600, 10000), 2: (3700, 10000)}

    def test_overrides_change_the_quality(self, db):
        _seed(db, _activity(1, START))
        _seed(
            db,
            _lap(11, 1, "interval", 15, 2500),
            _lap(12, 1, "interval", 30, 6000),
            ActivityTag(activity_id=1, tag="workout"),
        )
        assert self._log(db) == {1: (2700, 8500)}

        intensity_crud.set_lap_intensity(11, LapIntensityKey.WARMUP, OWNER, db)

        assert self._log(db) == {1: (1800, 6000)}


def _build_app(mock_db, user_id: int = OWNER) -> FastAPI:
    import auth.dependencies as auth_deps
    import core.database as core_db
    from homelab.lap_intensity import router

    app = FastAPI()
    app.include_router(router.router, prefix="/homelab/lap_intensity")
    app.dependency_overrides[auth_deps.check_scopes] = lambda: None
    app.dependency_overrides[auth_deps.get_sub_from_access_token] = lambda: user_id
    app.dependency_overrides[core_db.get_db] = lambda: mock_db
    return app


@pytest.fixture
def mock_db():
    return MagicMock(spec=Session)


class TestRoutes:
    @patch("homelab.lap_intensity.crud.get_activity_lap_intensities", return_value=[])
    def test_get_passes_activity_and_token_user(self, mock_get, mock_db):
        resp = TestClient(_build_app(mock_db, user_id=7)).get("/homelab/lap_intensity?activity_id=3")
        assert resp.status_code == 200
        mock_get.assert_called_once_with(3, 7, mock_db)

    @pytest.mark.parametrize("query", ["", "?activity_id=0", "?activity_id=x"])
    def test_get_validates_the_activity_id(self, mock_db, query):
        assert TestClient(_build_app(mock_db)).get(f"/homelab/lap_intensity{query}").status_code == 422

    @patch("homelab.lap_intensity.crud.set_lap_intensity")
    @pytest.mark.parametrize(
        ("body", "expected"), [({"intensity": "rest"}, LapIntensityKey.REST), ({"intensity": None}, None)]
    )
    def test_put_sets_or_clears_as_the_token_user(self, mock_set, mock_db, body, expected):
        mock_set.return_value = LapIntensityRead(
            lap_id=4, intensity="rest", recorded=None, source=LapIntensitySource.OVERRIDE
        )
        resp = TestClient(_build_app(mock_db, user_id=7)).put("/homelab/lap_intensity/4", json=body)
        assert resp.status_code == 200
        assert resp.json() == {"lap_id": 4, "intensity": "rest", "recorded": None, "source": "override"}
        mock_set.assert_called_once_with(4, expected, 7, mock_db)

    @pytest.mark.parametrize("body", [{"intensity": "tempo"}, {}, {"intensity": "rest", "extra": 1}])
    def test_put_validates_body(self, mock_db, body):
        assert TestClient(_build_app(mock_db)).put("/homelab/lap_intensity/4", json=body).status_code == 422

    def test_routes_are_registered_in_the_api_router(self):
        from core.routes import router as api_router

        app = FastAPI()
        app.include_router(api_router)
        paths = app.openapi()["paths"]
        assert set(paths["/api/v1/homelab/lap_intensity"]) == {"get"}
        assert set(paths["/api/v1/homelab/lap_intensity/{lap_id}"]) == {"put"}
