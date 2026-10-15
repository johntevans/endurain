"""Homelab fork: training log (local-date bucketing, scoping, tags, routes).

The date window and the owner/hidden scoping are SQL ``WHERE`` clauses, so
they run against a real in-memory SQLite database with the ``homelab`` schema
attached, as in ``test_activity_tags.py``.
"""

from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

import activities.activity.models as activities_models
from homelab.activity_tags.models import ActivityTag
from homelab.activity_tags.schema import ActivityTagKey
from homelab.database import HomelabBase
from homelab.training_log import crud as training_log_crud
from homelab.training_log.schema import TrainingLogRange
from tests._helpers.db import create_sqlite_session

OWNER = 1
OTHER = 2


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


def _activity(activity_id: int, start_time: datetime, **overrides) -> activities_models.Activity:
    fields = {
        "id": activity_id,
        "user_id": OWNER,
        "name": f"Activity {activity_id}",
        "distance": 10000,
        "activity_type": 1,
        "start_time": start_time,
        "end_time": start_time,
        "created_at": datetime(2024, 1, 1, tzinfo=UTC),
        "total_elapsed_time": Decimal("3700"),
        "total_timer_time": Decimal("3600"),
        "elevation_gain": 50,
        "visibility": 0,
        "is_hidden": False,
        "timezone": "UTC",
        **dict.fromkeys(
            [
                "hide_start_time",
                "hide_location",
                "hide_map",
                "hide_hr",
                "hide_power",
                "hide_cadence",
                "hide_elevation",
                "hide_speed",
                "hide_pace",
                "hide_laps",
                "hide_workout_sets_steps",
                "hide_gear",
            ],
            False,
        ),
    }
    fields.update(overrides)
    return activities_models.Activity(**fields)


def _ids(result) -> list[int]:
    return [item.id for item in result]


class TestGetTrainingLogActivities:
    def test_returns_fields_and_tags_in_chronological_order(self, db):
        db.add_all(
            [
                _activity(2, datetime(2026, 10, 14, 7, tzinfo=UTC), name="Tempo"),
                _activity(1, datetime(2026, 10, 12, 7, tzinfo=UTC), name="Easy", elevation_gain=None),
            ]
        )
        db.commit()
        db.add_all([ActivityTag(activity_id=2, tag="long_run"), ActivityTag(activity_id=2, tag="race")])
        db.commit()

        result = training_log_crud.get_training_log_activities(OWNER, date(2026, 10, 12), date(2026, 10, 18), db)

        assert _ids(result) == [1, 2]
        easy, tempo = result
        assert easy.name == "Easy"
        assert easy.local_date == date(2026, 10, 12)
        assert easy.start_time == "2026-10-12T07:00:00"
        assert easy.distance == 10000
        assert easy.total_timer_time == 3600.0
        assert easy.total_elapsed_time == 3700.0
        assert easy.elevation_gain is None
        assert easy.tags == []
        assert tempo.tags == [ActivityTagKey.RACE, ActivityTagKey.LONG_RUN]

    def test_buckets_by_the_activity_local_date(self, db):
        # 2026-10-12 23:30 UTC is already Tuesday 2026-10-13 08:30 in Tokyo, and
        # 2026-10-19 02:00 UTC is still Sunday 2026-10-18 evening in Los Angeles.
        db.add_all(
            [
                _activity(1, datetime(2026, 10, 12, 23, 30, tzinfo=UTC), timezone="Asia/Tokyo"),
                _activity(2, datetime(2026, 10, 19, 2, tzinfo=UTC), timezone="America/Los_Angeles"),
                # Saturday 2026-10-11 20:00 in Los Angeles: before the window locally
                # although its UTC date (10-12) is inside it.
                _activity(3, datetime(2026, 10, 12, 3, tzinfo=UTC), timezone="America/Los_Angeles"),
                # Monday 2026-10-19 08:00 in Tokyo: after the window locally although
                # its UTC date (10-18) is inside it.
                _activity(4, datetime(2026, 10, 18, 23, tzinfo=UTC), timezone="Asia/Tokyo"),
            ]
        )
        db.commit()

        result = training_log_crud.get_training_log_activities(OWNER, date(2026, 10, 12), date(2026, 10, 18), db)

        assert _ids(result) == [1, 2]
        assert result[0].local_date == date(2026, 10, 13)
        assert result[0].start_time == "2026-10-13T08:30:00"
        assert result[1].local_date == date(2026, 10, 18)

    def test_missing_or_unknown_timezone_uses_the_server_zone(self, db):
        db.add_all(
            [
                _activity(1, datetime(2026, 10, 12, 7, tzinfo=UTC), timezone=None),
                _activity(2, datetime(2026, 10, 13, 7, tzinfo=UTC), timezone="Not/AZone"),
            ]
        )
        db.commit()

        with patch("core.config.settings.TZ", "UTC"):
            result = training_log_crud.get_training_log_activities(OWNER, date(2026, 10, 12), date(2026, 10, 18), db)

        assert [item.local_date for item in result] == [date(2026, 10, 12), date(2026, 10, 13)]

    def test_only_the_owners_non_hidden_activities(self, db):
        db.add_all(
            [
                _activity(1, datetime(2026, 10, 12, 7, tzinfo=UTC)),
                _activity(2, datetime(2026, 10, 13, 7, tzinfo=UTC), user_id=OTHER),
                _activity(3, datetime(2026, 10, 14, 7, tzinfo=UTC), is_hidden=True),
                _activity(4, datetime(2026, 10, 15, 7, tzinfo=UTC), visibility=2),
            ]
        )
        db.commit()

        result = training_log_crud.get_training_log_activities(OWNER, date(2026, 10, 12), date(2026, 10, 18), db)

        assert _ids(result) == [1, 4]

    def test_empty_window(self, db):
        assert training_log_crud.get_training_log_activities(OWNER, date(2026, 1, 1), date(2026, 1, 7), db) == []

    def test_database_error_is_a_500(self):
        broken = MagicMock()
        broken.execute.side_effect = SQLAlchemyError("boom")
        with pytest.raises(HTTPException) as err:
            training_log_crud.get_training_log_activities(OWNER, date(2026, 1, 1), date(2026, 1, 7), broken)
        assert err.value.status_code == 500


class TestGetTrainingLogRange:
    def test_first_and_last_local_dates(self, db):
        db.add_all(
            [
                _activity(1, datetime(2021, 3, 1, 23, tzinfo=UTC), timezone="Asia/Tokyo"),
                _activity(2, datetime(2026, 10, 15, 3, tzinfo=UTC), timezone="America/Los_Angeles"),
                _activity(3, datetime(2020, 1, 1, tzinfo=UTC), is_hidden=True),
                _activity(4, datetime(2027, 1, 1, tzinfo=UTC), user_id=OTHER),
            ]
        )
        db.commit()

        result = training_log_crud.get_training_log_range(OWNER, db)

        assert result == TrainingLogRange(first_date=date(2021, 3, 2), last_date=date(2026, 10, 14))

    def test_no_activities(self, db):
        assert training_log_crud.get_training_log_range(OWNER, db) == TrainingLogRange()

    def test_database_error_is_a_500(self):
        broken = MagicMock()
        broken.execute.side_effect = SQLAlchemyError("boom")
        with pytest.raises(HTTPException) as err:
            training_log_crud.get_training_log_range(OWNER, broken)
        assert err.value.status_code == 500


def _build_app(mock_db, user_id: int = OWNER) -> FastAPI:
    import auth.dependencies as auth_deps
    import core.database as core_db
    from homelab.training_log import router

    app = FastAPI()
    app.include_router(router.router, prefix="/homelab/training_log")
    app.dependency_overrides[auth_deps.check_scopes] = lambda: None
    app.dependency_overrides[auth_deps.get_sub_from_access_token] = lambda: user_id
    app.dependency_overrides[core_db.get_db] = lambda: mock_db
    return app


@pytest.fixture
def mock_db():
    return MagicMock(spec=Session)


class TestRoutes:
    @patch("homelab.training_log.crud.get_training_log_activities", return_value=[])
    def test_get_passes_dates_and_token_user(self, mock_get, mock_db):
        resp = TestClient(_build_app(mock_db, user_id=7)).get(
            "/homelab/training_log?start_date=2025-12-29&end_date=2026-12-27"
        )
        assert resp.status_code == 200
        assert resp.json() == []
        mock_get.assert_called_once_with(7, date(2025, 12, 29), date(2026, 12, 27), mock_db)

    @pytest.mark.parametrize(
        "query",
        [
            "",
            "?start_date=2026-01-01",
            "?start_date=bad&end_date=2026-01-01",
            "?start_date=2026-01-02&end_date=2026-01-01",
            "?start_date=2025-01-01&end_date=2026-02-05",
        ],
    )
    def test_get_validates_the_range(self, mock_db, query):
        assert TestClient(_build_app(mock_db)).get(f"/homelab/training_log{query}").status_code == 422

    def test_get_allows_a_single_day(self, mock_db):
        with patch("homelab.training_log.crud.get_training_log_activities", return_value=[]):
            resp = TestClient(_build_app(mock_db)).get(
                "/homelab/training_log?start_date=2026-01-01&end_date=2026-01-01"
            )
        assert resp.status_code == 200

    @patch(
        "homelab.training_log.crud.get_training_log_range",
        return_value=TrainingLogRange(first_date=date(2021, 3, 2), last_date=date(2026, 10, 14)),
    )
    def test_range(self, mock_range, mock_db):
        resp = TestClient(_build_app(mock_db, user_id=7)).get("/homelab/training_log/range")
        assert resp.status_code == 200
        assert resp.json() == {"first_date": "2021-03-02", "last_date": "2026-10-14"}
        mock_range.assert_called_once_with(7, mock_db)

    def test_routes_are_registered_in_the_api_router(self):
        from core.routes import router as api_router

        app = FastAPI()
        app.include_router(api_router)
        paths = app.openapi()["paths"]
        assert set(paths["/api/v1/homelab/training_log"]) == {"get"}
        assert set(paths["/api/v1/homelab/training_log/range"]) == {"get"}
