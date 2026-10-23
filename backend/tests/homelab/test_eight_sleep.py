"""Homelab fork: Eight Sleep sleep sync (mapping, reconciliation, Garmin hand-off).

Fixtures are synthetic but shaped like real ``/trends`` day records: one day
per wake-up date, ``mainSessionId`` naming the session the day totals cover.
Reconciliation runs against a real in-memory SQLite database, because what it
deletes or keeps is decided by SQL ``WHERE`` clauses.
"""

from collections.abc import Iterator
from datetime import UTC, date, datetime
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

import health.health_sleep.models as health_sleep_models
from homelab.database import HomelabBase
from homelab.eight_sleep import client as eight_sleep_client
from homelab.eight_sleep import mapping as eight_sleep_mapping
from homelab.eight_sleep import router as metric_router
from homelab.eight_sleep import sync as eight_sleep_sync
from homelab.eight_sleep.models import SleepHeartRate, SleepHrv
from tests._helpers.db import create_sqlite_session

USER = 1
TZ = "America/Los_Angeles"


def _session(session_id: str, ts: str, **overrides) -> dict:
    session = {
        "id": session_id,
        "ts": ts,
        "timezone": TZ,
        "duration": 33000,
        "stages": [
            {"stage": "awake", "duration": 600},
            {"stage": "light", "duration": 1800},
            {"stage": "out", "duration": 300},
            {"stage": "deep", "duration": 1200},
            {"stage": "rem", "duration": 900},
        ],
        "timeseries": {
            "heartRate": [["2026-10-08T04:00:00.000Z", 44.6], ["2026-10-08T05:00:00.000Z", 50.2]],
            "respiratoryRate": [["2026-10-08T04:00:00.000Z", 17.4]],
        },
    }
    session.update(overrides)
    return session


def _day(day: str, sessions: list[dict], main: str | None = None, **overrides) -> dict:
    record = {
        "day": day,
        "score": 88,
        "sleepDuration": 24000,
        "deepDuration": 3600,
        "lightDuration": 14400,
        "remDuration": 6000,
        "wasoDuration": 900,
        "wakeupCount": 2,
        "sleepStart": f"{day}T04:10:00.000Z",
        "sleepEnd": f"{day}T11:30:00.000Z",
        "mainSessionId": main if main is not None else sessions[0]["id"],
        "sessions": sessions,
        "sleepQualityScore": {
            "hrv": {
                "current": 71.5,
                "inclusive7DayAverage": 72.7,
                "average": 72.9,
                "lowerRange": 65.6,
                "upperRange": 80.2,
                "upperBound": 9999,
            },
            "heartRate": {
                "current": 43,
                "inclusive7DayAverage": 43.6,
                "average": 44.1,
                "lowerRange": 42.3,
                "upperRange": 45.9,
                "lowerBound": -9999,
            },
        },
    }
    record.update(overrides)
    return record


def _night(day: str, **overrides) -> dict:
    """A normal overnight: in bed 20:50 PDT the evening before ``day``."""
    return _day(day, [_session(f"n-{day}", f"{day}T03:50:00.000Z")], **overrides)


class TestMapDay:
    def test_overnight_session_maps_day_totals_and_main_session(self):
        result = eight_sleep_mapping.map_day(_night("2026-10-08"), TZ)

        sleep = result.sleep
        assert result.skip is None
        assert sleep.date == date(2026, 10, 8)
        assert sleep.total_sleep_seconds == 24000
        assert (sleep.deep_sleep_seconds, sleep.light_sleep_seconds, sleep.rem_sleep_seconds) == (3600, 14400, 6000)
        assert sleep.awake_sleep_seconds == 900
        assert sleep.awake_count == 2
        assert (sleep.avg_heart_rate, sleep.min_heart_rate, sleep.max_heart_rate) == (47, 45, 50)
        assert sleep.avg_respiration == 17
        assert sleep.source == "eight_sleep"
        # Eight Sleep's score, not Endurain's recomputation
        assert sleep.sleep_score_overall == 88
        assert sleep.sleep_score_quality == "GOOD"
        assert sleep.sleep_score_duration is not None

    def test_hrv_and_resting_hr_are_eight_sleeps_own_figures(self):
        result = eight_sleep_mapping.map_day(_night("2026-10-08"), TZ)

        # 71.5 is what the app shows as "72"; the timeseries mean was 74.
        assert result.hrv.value == 71.5
        assert (result.hrv.avg_7d, result.hrv.baseline) == (72.7, 72.9)
        assert (result.hrv.range_low, result.hrv.range_high) == (65.6, 80.2)
        assert result.sleep.resting_heart_rate == 43
        assert (result.heart_rate.value, result.heart_rate.avg_7d) == (43, 43.6)
        assert (result.heart_rate.range_low, result.heart_rate.range_high) == (42.3, 45.9)

    def test_missing_or_sentinel_quality_values_are_none(self):
        day = _night("2026-10-08")
        day["sleepQualityScore"] = {"hrv": {"current": 0, "upperRange": 9999}, "heartRate": {"current": -9999}}

        result = eight_sleep_mapping.map_day(day, TZ)
        assert result.hrv is None
        assert result.heart_rate is None
        assert result.sleep.resting_heart_rate is None

    def test_local_times_are_wall_clock_labelled_utc_like_garmin(self):
        sleep = eight_sleep_mapping.map_day(_night("2026-10-08"), TZ).sleep

        assert sleep.sleep_start_time_gmt == datetime(2026, 10, 8, 4, 10, tzinfo=UTC)
        assert sleep.sleep_start_time_local == datetime(2026, 10, 7, 21, 10, tzinfo=UTC)

    def test_out_of_bed_advances_the_clock_but_is_not_a_stage(self):
        stages = eight_sleep_mapping.map_day(_night("2026-10-08"), TZ).sleep.sleep_stages

        assert [s.stage_type for s in stages] == [3, 1, 0, 2]
        deep = stages[2]
        # 600 awake + 1800 light + 300 out after 03:50
        assert deep.start_time_gmt == datetime(2026, 10, 8, 4, 35, tzinfo=UTC)
        assert deep.duration_seconds == 1200

    def test_daytime_main_session_is_skipped(self):
        day = _day("2026-10-20", [_session("d", "2026-10-20T18:43:00.000Z")], score=28)

        assert eight_sleep_mapping.map_day(day, TZ).skip is eight_sleep_mapping.Skip.DAYTIME

    def test_second_daytime_session_does_not_displace_the_night(self):
        day = _day(
            "2026-10-11",
            [_session("night", "2026-10-11T03:44:00.000Z"), _session("day", "2026-10-11T17:14:00.000Z")],
            main="night",
        )

        result = eight_sleep_mapping.map_day(day, TZ)
        assert result.sleep is not None
        assert result.sleep.sleep_stages[0].start_time_gmt == datetime(2026, 10, 11, 3, 44, tzinfo=UTC)

    def test_session_that_starts_after_midnight_is_still_a_night(self):
        day = _day("2026-10-09", [_session("late", "2026-10-09T09:30:00.000Z")])  # 02:30 PDT

        assert eight_sleep_mapping.map_day(day, TZ).sleep is not None

    def test_processing_day_is_skipped(self):
        day = _night("2026-10-22", processing=True)

        assert eight_sleep_mapping.map_day(day, TZ).skip is eight_sleep_mapping.Skip.PROCESSING

    def test_incomplete_flag_alone_does_not_block_import(self):
        # Seen on finished 2024 nights that have a score and full stages.
        day = _night("2024-06-05", incomplete=True)
        day["sessions"][0]["incomplete"] = True

        assert eight_sleep_mapping.map_day(day, TZ).sleep is not None

    def test_missing_main_session_is_skipped(self):
        day = _night("2026-10-08", mainSessionId="gone")

        assert eight_sleep_mapping.map_day(day, TZ).skip is eight_sleep_mapping.Skip.NO_MAIN_SESSION

    def test_implausible_heart_rate_is_dropped_not_fatal(self):
        day = _night("2026-10-08")
        day["sessions"][0]["timeseries"]["heartRate"] = [["t", 5.0]]

        sleep = eight_sleep_mapping.map_day(day, TZ).sleep
        assert sleep.avg_heart_rate is None


@pytest.fixture
def db() -> Iterator[Session]:
    session = create_sqlite_session()
    session.execute(text("ATTACH DATABASE ':memory:' AS homelab"))
    HomelabBase.metadata.create_all(session.connection())
    session.commit()
    try:
        yield session
    finally:
        session.close()
        session.bind.dispose()


def _row(db: Session, day: date, source: str | None, total: int = 1000) -> None:
    db.add(health_sleep_models.HealthSleep(user_id=USER, date=day, source=source, total_sleep_seconds=total))
    db.commit()


def _rows(db: Session) -> dict[date, tuple[str | None, int | None]]:
    db.expire_all()
    rows = db.execute(select(health_sleep_models.HealthSleep)).scalars()
    return {r.date: (r.source, r.total_sleep_seconds) for r in rows}


WINDOW = (date(2026, 10, 1), date(2026, 10, 22))


def _orm_create(user_id, sleep, db):
    db.add(
        health_sleep_models.HealthSleep(
            user_id=user_id, date=sleep.date, source=sleep.source, total_sleep_seconds=sleep.total_sleep_seconds
        )
    )
    db.commit()


def _orm_edit(user_id, sleep, db):
    row = db.get(health_sleep_models.HealthSleep, sleep.id)
    row.source, row.total_sleep_seconds = sleep.source, sleep.total_sleep_seconds
    db.commit()


class TestReconcile:
    @pytest.fixture(autouse=True)
    def _sqlite_writes(self):
        # Upstream's create/edit dump with mode="json" (dates as strings), which
        # Postgres accepts and SQLite refuses. Delete is upstream's own.
        with (
            patch.object(eight_sleep_sync.health_sleep_crud, "create_health_sleep", side_effect=_orm_create),
            patch.object(eight_sleep_sync.health_sleep_crud, "edit_health_sleep", side_effect=_orm_edit),
        ):
            yield

    def _reconcile(self, db, days):
        return eight_sleep_sync.reconcile(USER, *WINDOW, days, TZ, db)

    def test_creates_then_updates_from_eight_sleep(self, db):
        self._reconcile(db, [_night("2026-10-08")])
        counts = self._reconcile(db, [_night("2026-10-08", sleepDuration=25000)])

        assert counts["updated"] == 1
        assert _rows(db) == {date(2026, 10, 8): ("eight_sleep", 25000)}

    def test_night_gone_from_eight_sleep_is_deleted(self, db):
        self._reconcile(db, [_night("2026-10-08"), _night("2026-10-09")])
        counts = self._reconcile(db, [_night("2026-10-09")])

        assert counts["deleted"] == 1
        assert set(_rows(db)) == {date(2026, 10, 9)}

    def test_previously_imported_night_now_daytime_is_deleted(self, db):
        self._reconcile(db, [_night("2026-10-20")])
        daytime = _day("2026-10-20", [_session("d", "2026-10-20T18:43:00.000Z")])
        self._reconcile(db, [_night("2026-10-09"), daytime])

        assert set(_rows(db)) == {date(2026, 10, 9)}

    def test_processing_day_leaves_existing_row_alone(self, db):
        self._reconcile(db, [_night("2026-10-22")])
        counts = self._reconcile(db, [_night("2026-10-22", processing=True)])

        assert counts["processing"] == 1
        assert date(2026, 10, 22) in _rows(db)

    def test_manual_entry_is_never_overwritten_or_deleted(self, db):
        _row(db, date(2026, 10, 8), None, total=111)
        _row(db, date(2026, 10, 9), None, total=222)
        self._reconcile(db, [_night("2026-10-08"), _night("2026-10-10")])

        rows = _rows(db)
        assert rows[date(2026, 10, 8)] == (None, 111)
        assert rows[date(2026, 10, 9)] == (None, 222)

    def test_garmin_row_is_replaced_but_never_deleted(self, db):
        _row(db, date(2026, 10, 8), "garmin")
        _row(db, date(2026, 10, 9), "garmin")
        self._reconcile(db, [_night("2026-10-08"), _night("2026-10-10")])

        rows = _rows(db)
        assert rows[date(2026, 10, 8)][0] == "eight_sleep"
        assert rows[date(2026, 10, 9)][0] == "garmin"

    def test_empty_response_deletes_nothing(self, db):
        self._reconcile(db, [_night("2026-10-08"), _night("2026-10-09")])
        counts = self._reconcile(db, [])

        assert counts["refused empty"] == 1
        assert len(_rows(db)) == 2

    def test_hrv_follows_the_imported_nights(self, db):
        self._reconcile(db, [_night("2026-10-08"), _night("2026-10-09")])
        night = _night("2026-10-09")
        night["sleepQualityScore"]["hrv"]["current"] = 80.0
        counts = self._reconcile(db, [night])

        rows = {r.date: r.hrv_ms for r in db.execute(select(SleepHrv)).scalars()}
        assert rows == {date(2026, 10, 9): 80.0}
        assert counts["hrv deleted"] == 1
        hr = {
            r.date: (r.hr_bpm, r.avg_7d_bpm, r.range_low_bpm, r.range_high_bpm)
            for r in db.execute(select(SleepHeartRate)).scalars()
        }
        assert hr == {date(2026, 10, 9): (43, 43.6, 42.3, 45.9)}
        assert counts["heart rate deleted"] == 1

    def test_hrv_is_kept_beside_a_manual_sleep_entry(self, db):
        _row(db, date(2026, 10, 8), None)
        self._reconcile(db, [_night("2026-10-08")])

        assert db.execute(select(SleepHrv.date)).scalars().all() == [date(2026, 10, 8)]

    def test_daytime_night_gets_no_hrv(self, db):
        daytime = _day("2026-10-20", [_session("d", "2026-10-20T18:43:00.000Z")])
        self._reconcile(db, [daytime])

        assert db.execute(select(SleepHrv)).scalars().all() == []
        assert db.execute(select(SleepHeartRate)).scalars().all() == []

    def test_processing_night_keeps_its_hrv(self, db):
        self._reconcile(db, [_night("2026-10-22")])
        self._reconcile(db, [_night("2026-10-22", processing=True)])

        assert db.execute(select(SleepHrv.date)).scalars().all() == [date(2026, 10, 22)]

    def test_rows_outside_the_window_are_untouched(self, db):
        _row(db, date(2026, 9, 1), "eight_sleep")
        self._reconcile(db, [_night("2026-10-08")])

        assert date(2026, 9, 1) in _rows(db)


class TestSafety:
    def test_failed_fetch_writes_nothing(self, db):
        self_db = db
        _row(db, date(2026, 10, 8), "eight_sleep")
        with (
            patch.dict("os.environ", {"EIGHT_SLEEP_EMAIL": "a@b.c", "EIGHT_SLEEP_PASSWORD": "x"}),
            patch.object(eight_sleep_sync, "SessionLocal", return_value=self_db),
            patch.object(eight_sleep_sync, "_target_user_id", return_value=USER),
            patch.object(eight_sleep_client, "fetch_days", side_effect=eight_sleep_client.EightSleepError("HTTP 503")),
            patch.object(eight_sleep_sync.core_logger, "print_to_log") as log,
        ):
            eight_sleep_sync.sync_recent()

        assert "failed" in log.call_args.args[0]
        assert date(2026, 10, 8) in _rows(db)

    def test_no_credentials_means_no_sync_and_garmin_keeps_sleep(self):
        with (
            patch.dict("os.environ", {"EIGHT_SLEEP_EMAIL": "", "EIGHT_SLEEP_PASSWORD": ""}),
            patch.object(eight_sleep_client, "fetch_days") as fetch,
        ):
            eight_sleep_sync.sync_recent()
            assert eight_sleep_client.owns_sleep() is False
        fetch.assert_not_called()

    def test_credentials_hand_sleep_to_eight_sleep(self):
        with patch.dict("os.environ", {"EIGHT_SLEEP_EMAIL": "a@b.c", "EIGHT_SLEEP_PASSWORD": "x"}):
            assert eight_sleep_client.owns_sleep() is True


class TestClient:
    def test_fetch_days_chunks_long_windows(self):
        calls = []

        def fake_get(_client, path, params):
            calls.append((params["from"], params["to"]))
            return {"days": []}

        with patch.object(eight_sleep_client, "_get", side_effect=fake_get):
            eight_sleep_client.fetch_days(date(2026, 1, 1), date(2026, 3, 1), TZ)

        assert calls == [("2026-01-01", "2026-01-30"), ("2026-01-31", "2026-03-01")]

    def test_malformed_response_raises(self):
        with (
            patch.object(eight_sleep_client, "_get", return_value={"error": "x"}),
            pytest.raises(eight_sleep_client.EightSleepError),
        ):
            eight_sleep_client.fetch_days(date(2026, 1, 1), date(2026, 1, 2), TZ)


class TestMetricRoutes:
    def _client(self, db):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        import auth.dependencies as auth_deps
        import core.database as core_db

        app = FastAPI()
        app.include_router(metric_router.hrv_router, prefix="/hrv")
        app.include_router(metric_router.heart_rate_router, prefix="/hr")
        app.dependency_overrides[auth_deps.check_scopes] = lambda: None
        app.dependency_overrides[auth_deps.get_sub_from_access_token] = lambda: USER
        app.dependency_overrides[core_db.get_db] = lambda: db
        return TestClient(app)

    def _add(self, db, day: date, hrv: float, user: int = USER):
        db.add(SleepHrv(user_id=user, date=day, hrv_ms=hrv, source="eight_sleep"))
        db.add(SleepHeartRate(user_id=user, date=day, hr_bpm=hrv / 2, source="eight_sleep"))
        db.commit()

    def test_list_is_newest_first_owner_only_and_paginated(self, db):
        self._add(db, date(2026, 10, 7), 70.0)
        self._add(db, date(2026, 10, 8), 71.5)
        self._add(db, date(2026, 10, 9), 75.0)
        self._add(db, date(2026, 10, 9), 99.0, user=2)

        hrv = self._client(db).get("/hrv", params={"page_number": 1, "num_records": 2}).json()
        hr = self._client(db).get("/hr", params={"page_number": 1, "num_records": 2}).json()

        assert hrv["total"] == 3
        assert [(r["date"], r["hrv_ms"]) for r in hrv["records"]] == [("2026-10-09", 75.0), ("2026-10-08", 71.5)]
        assert [(r["date"], r["hr_bpm"]) for r in hr["records"]] == [("2026-10-09", 37.5), ("2026-10-08", 35.75)]

    def test_interval_limits_the_window(self, db):
        self._add(db, date(2020, 1, 1), 70.0)
        self._add(db, eight_sleep_sync._today(), 71.5)

        assert self._client(db).get("/hr", params={"interval": "last_7_days"}).json()["total"] == 1

    def test_latest_is_the_most_recent_night_or_null(self, db):
        client = self._client(db)
        assert client.get("/hr/latest").json() is None
        self._add(db, date(2026, 10, 7), 70.0)
        self._add(db, date(2026, 10, 9), 75.0)

        assert client.get("/hrv/latest").json()["hrv_ms"] == 75.0
        assert client.get("/hr/latest").json()["hr_bpm"] == 37.5


class TestDashboard:
    def test_sleep_without_garmin_hrv_status_still_reaches_the_dashboard(self, mock_db):
        # Upstream returned no sleep at all unless hrv_status (Garmin-only) was set,
        # which blanked the Sleep and Resting HR tiles for every Eight Sleep night.
        from fastapi.testclient import TestClient

        from tests.health.test_health_router import _build_app

        sleep = MagicMock(
            total_sleep_seconds=24210, resting_heart_rate=43, hrv_status=None, avg_skin_temp_deviation=None
        )
        with (
            patch("health.router.health_sleep_crud.get_health_sleep_by_date_and_user_id", return_value=sleep),
            patch("health.router.health_weight_crud.get_latest_weight_by_user_id", return_value=None),
            patch("health.router.health_steps_crud.get_health_steps_by_date_and_user_id", return_value=None),
            patch("health.router.health_fasting_crud.get_active_fasting_by_user_id", return_value=None),
            patch("health.router.health_water_crud.get_health_water_by_date_and_user_id", return_value=None),
            patch("health.router.health_poop_crud.get_health_poop_by_date_and_user_id", return_value=None),
        ):
            response = TestClient(_build_app(mock_db)).get("/health/stats/daily", headers={"Authorization": "Bearer x"})

        assert response.json()["sleep"] == {
            "total_sleep_seconds": 24210,
            "resting_heart_rate": 43,
            "hrv_status": None,
            "avg_skin_temp_deviation": None,
        }
