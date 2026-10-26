"""Homelab fork: Withings weight sync (fetch, first-weigh-in mapping, reconciliation)."""

from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select, text
from sqlalchemy.orm import Session

import health.health_weight.models as health_weight_models
from homelab.database import HomelabBase
from homelab.withings import client as withings_client
from homelab.withings import mapping as withings_mapping
from homelab.withings import sync as withings_sync
from homelab.withings import tokens as withings_tokens
from tests._helpers.db import create_sqlite_session

USER = 1
TZ = "America/Los_Angeles"
CFG = withings_client.WithingsConfig("cid", "csecret", "https://tempo.example/cb")


def _ts(local: str) -> int:
    """A Los Angeles wall-clock time as a Unix timestamp."""
    from zoneinfo import ZoneInfo

    return int(datetime.fromisoformat(local).replace(tzinfo=ZoneInfo(TZ)).timestamp())


def _group(local: str, kg: float = 80.0, attrib: int = 0, body: bool = True) -> dict:
    measures = [{"type": 1, "value": int(kg * 1000), "unit": -3}]
    if body:
        measures += [
            {"type": 6, "value": 1850, "unit": -2},  # 18.5 %
            {"type": 76, "value": 6200, "unit": -2},  # 62.0 kg muscle
            {"type": 77, "value": 4800, "unit": -2},  # 48.0 kg water
            {"type": 88, "value": 330, "unit": -2},  # 3.3 kg bone
            {"type": 170, "value": 7, "unit": 0},  # visceral 7
        ]
    return {"grpid": _ts(local), "attrib": attrib, "date": _ts(local), "category": 1, "measures": measures}


@pytest.fixture(autouse=True)
def fernet_key(monkeypatch):
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())


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


class TestMapping:
    def test_decodes_units_and_converts_water_to_a_percentage(self):
        by_date, skipped = withings_mapping.map_groups([_group("2026-10-08T06:10:00")], TZ)

        weight = by_date[date(2026, 10, 8)].weight
        assert skipped == 0
        assert weight.weight == 80.0
        assert weight.body_fat == 18.5
        assert weight.muscle_mass == 62.0
        assert weight.body_water == 60.0  # 48 kg of 80 kg
        assert weight.bone_mass == 3.3
        assert weight.visceral_fat == 7
        assert weight.source == "withings"
        assert weight.bmi is None  # left to upstream's crud, from the user's height

    def test_the_first_weigh_in_of_the_local_day_wins(self):
        groups = [
            _group("2026-10-08T19:30:00", kg=81.4),
            _group("2026-10-08T06:10:00", kg=80.2),
            _group("2026-10-08T12:00:00", kg=80.9),
        ]
        by_date, _ = withings_mapping.map_groups(groups, TZ)

        assert by_date[date(2026, 10, 8)].weight.weight == 80.2

    def test_days_follow_local_time_not_utc(self):
        # 22:30 in Los Angeles is already the next day in UTC.
        by_date, _ = withings_mapping.map_groups([_group("2026-10-08T22:30:00")], TZ)

        assert list(by_date) == [date(2026, 10, 8)]

    def test_ambiguous_weigh_ins_are_skipped_but_hand_entries_kept(self):
        groups = [_group("2026-10-08T06:00:00", attrib=1), _group("2026-10-09T06:00:00", attrib=2)]
        by_date, skipped = withings_mapping.map_groups(groups, TZ)

        assert skipped == 1
        assert list(by_date) == [date(2026, 10, 9)]

    def test_a_weigh_in_without_body_composition_still_imports(self):
        by_date, _ = withings_mapping.map_groups([_group("2026-10-08T06:00:00", body=False)], TZ)

        weight = by_date[date(2026, 10, 8)].weight
        assert weight.weight == 80.0
        assert weight.body_fat is None
        assert weight.body_water is None


class TestFetch:
    def _response(self, body, status=0, http=200):
        response = MagicMock(status_code=http)
        response.json.return_value = {"status": status, "body": body}
        return response

    def test_pages_until_done(self):
        pages = [
            self._response({"measuregrps": [_group("2026-10-07T06:00:00")], "more": 1, "offset": 1, "timezone": TZ}),
            self._response({"measuregrps": [_group("2026-10-08T06:00:00")], "more": 0, "timezone": TZ}),
        ]
        with patch.object(withings_client.httpx, "post", side_effect=pages) as post:
            groups, tz = withings_client.get_measure_groups("tok")

        assert (len(groups), tz) == (2, TZ)
        assert post.call_args_list[1].kwargs["data"]["offset"] == 1
        assert post.call_args.kwargs["headers"] == {"Authorization": "Bearer tok"}

    @pytest.mark.parametrize("response", ["status", "http", "shape"])
    def test_any_failure_raises_rather_than_reading_as_empty(self, response):
        bad = {
            "status": self._response({}, status=401),
            "http": self._response({}, http=500),
            "shape": self._response({"nothing": True}),
        }[response]
        with (
            patch.object(withings_client.httpx, "post", return_value=bad),
            pytest.raises(withings_client.WithingsError),
        ):
            withings_client.get_measure_groups("tok")


def _orm_create(user_id, weight, db):
    db.add(
        health_weight_models.HealthWeight(user_id=user_id, date=weight.date, weight=weight.weight, source=weight.source)
    )
    db.commit()


def _orm_edit(user_id, weight, db):
    row = db.get(health_weight_models.HealthWeight, weight.id)
    row.weight, row.source = weight.weight, weight.source
    db.commit()


def _row(db, day: date, source: str | None, kg: float = 70.0):
    db.add(health_weight_models.HealthWeight(user_id=USER, date=day, weight=kg, source=source))
    db.commit()


def _rows(db) -> dict:
    db.expire_all()
    return {
        r.date: (r.source, float(r.weight)) for r in db.execute(select(health_weight_models.HealthWeight)).scalars()
    }


WINDOW = (date(2026, 10, 1), date(2026, 10, 25))


class TestReconcile:
    @pytest.fixture(autouse=True)
    def _sqlite_writes(self):
        # Upstream's create/edit dump with mode="json" (dates as strings), which
        # Postgres accepts and SQLite refuses. Delete is upstream's own.
        with (
            patch.object(withings_sync.health_weight_crud, "create_health_weight", side_effect=_orm_create),
            patch.object(withings_sync.health_weight_crud, "edit_health_weight", side_effect=_orm_edit),
        ):
            yield

    def _sync(self, db, *groups):
        by_date, _ = withings_mapping.map_groups(list(groups), TZ)
        return withings_sync.reconcile(USER, *WINDOW, by_date, db)

    def test_creates_then_updates(self, db):
        self._sync(db, _group("2026-10-08T06:00:00", kg=80.0))
        counts = self._sync(db, _group("2026-10-08T06:00:00", kg=79.5))

        assert counts["updated"] == 1
        assert _rows(db) == {date(2026, 10, 8): ("withings", 79.5)}

    def test_a_weigh_in_gone_from_withings_is_deleted(self, db):
        self._sync(db, _group("2026-10-08T06:00:00"), _group("2026-10-09T06:00:00"))
        counts = self._sync(db, _group("2026-10-09T06:00:00"))

        assert counts["deleted"] == 1
        assert set(_rows(db)) == {date(2026, 10, 9)}

    def test_hand_entered_endurain_weight_is_never_overwritten_or_deleted(self, db):
        _row(db, date(2026, 10, 8), None, kg=70.0)
        _row(db, date(2026, 10, 9), None, kg=71.0)
        self._sync(db, _group("2026-10-08T06:00:00"), _group("2026-10-10T06:00:00"))

        rows = _rows(db)
        assert rows[date(2026, 10, 8)] == (None, 70.0)
        assert rows[date(2026, 10, 9)] == (None, 71.0)

    def test_a_garmin_row_is_replaced_but_never_deleted(self, db):
        _row(db, date(2026, 10, 8), "garmin")
        _row(db, date(2026, 10, 9), "garmin")
        self._sync(db, _group("2026-10-08T06:00:00"), _group("2026-10-10T06:00:00"))

        rows = _rows(db)
        assert rows[date(2026, 10, 8)][0] == "withings"
        assert rows[date(2026, 10, 9)][0] == "garmin"

    def test_an_empty_answer_deletes_nothing(self, db):
        self._sync(db, _group("2026-10-08T06:00:00"), _group("2026-10-09T06:00:00"))
        counts = self._sync(db)

        assert counts["refused empty"] == 1
        assert len(_rows(db)) == 2

    def test_rows_outside_the_window_are_untouched(self, db):
        _row(db, date(2026, 9, 1), "withings")
        self._sync(db, _group("2026-10-08T06:00:00"))

        assert date(2026, 9, 1) in _rows(db)


class TestGating:
    def test_garmin_stands_aside_only_once_withings_is_linked(self, db, monkeypatch):
        monkeypatch.setattr(withings_client, "config", lambda: CFG)
        assert withings_tokens.owns_weight(USER, db) is False

        withings_tokens.save(
            USER,
            withings_client.TokenSet("w42", "a", "r", datetime.now(UTC) + timedelta(hours=3), "user.metrics"),
            db,
        )
        assert withings_tokens.owns_weight(USER, db) is True

        monkeypatch.setattr(withings_client, "config", lambda: None)
        assert withings_tokens.owns_weight(USER, db) is False

    def test_configured_but_unlinked_logs_a_warning_and_fetches_nothing(self, db, monkeypatch):
        monkeypatch.setattr(withings_client, "config", lambda: CFG)
        monkeypatch.setattr(withings_sync, "SessionLocal", lambda: db)
        monkeypatch.setattr(withings_sync, "_target_user_id", lambda _db: USER)
        with (
            patch.object(withings_client, "get_measure_groups") as fetch,
            patch.object(withings_sync.core_logger, "print_to_log") as log,
        ):
            withings_sync.sync_recent()

        fetch.assert_not_called()
        assert "not linked" in log.call_args.args[0]

    def test_a_failed_fetch_writes_nothing_and_logs_failed(self, db, monkeypatch):
        monkeypatch.setattr(withings_client, "config", lambda: CFG)
        monkeypatch.setattr(withings_sync, "SessionLocal", lambda: db)
        monkeypatch.setattr(withings_sync, "_target_user_id", lambda _db: USER)
        _row(db, date(2026, 10, 8), "withings")
        withings_tokens.save(
            USER,
            withings_client.TokenSet("w42", "a", "r", datetime.now(UTC) + timedelta(hours=3), "user.metrics"),
            db,
        )
        with (
            patch.object(withings_client, "get_measure_groups", side_effect=withings_client.WithingsError("HTTP 503")),
            patch.object(withings_sync.core_logger, "print_to_log") as log,
        ):
            withings_sync.sync_recent()

        assert "failed" in log.call_args.args[0]
        assert date(2026, 10, 8) in _rows(db)

    def test_unconfigured_does_nothing(self, monkeypatch):
        monkeypatch.setattr(withings_client, "config", lambda: None)
        with patch.object(withings_sync, "SessionLocal") as session:
            withings_sync.sync_recent()
        session.assert_not_called()
