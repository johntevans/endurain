"""Homelab fork: forwarding Withings weigh-ins to Garmin Connect."""

import os
import struct
import time
from datetime import UTC, date, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from homelab.withings import garmin_push

FIT_EPOCH = 631065600


def _group(utc: str, kg: float = 80.0, attrib: int = 0, body: bool = True) -> dict:
    ts = int(datetime.fromisoformat(utc).replace(tzinfo=UTC).timestamp())
    measures = [{"type": 1, "value": int(kg * 1000), "unit": -3}]
    if body:
        measures += [
            {"type": 6, "value": 1600, "unit": -2},
            {"type": 76, "value": 6400, "unit": -2},
            {"type": 77, "value": 4800, "unit": -2},
            {"type": 88, "value": 330, "unit": -2},
            {"type": 170, "value": 3, "unit": 0},
        ]
    return {"grpid": ts, "attrib": attrib, "date": ts, "category": 1, "measures": measures}


def _at(utc: str) -> datetime:
    return datetime.fromisoformat(utc).replace(tzinfo=UTC)


class TestWeighIns:
    def test_every_weigh_in_is_forwarded_not_just_the_first_of_the_day(self):
        weighs = garmin_push.weigh_ins([_group("2026-10-08T19:00:00"), _group("2026-10-08T13:00:00")])

        assert [w.at for w in weighs] == [_at("2026-10-08T13:00:00"), _at("2026-10-08T19:00:00")]

    def test_units_match_the_fit_weight_message(self):
        w = garmin_push.weigh_ins([_group("2026-10-08T13:00:00")])[0]

        assert (w.weight, w.percent_fat, w.percent_hydration) == (80.0, 16.0, 60.0)
        assert (w.bone_mass, w.muscle_mass, w.visceral_fat_rating) == (3.3, 64.0, 3)

    def test_ambiguous_weigh_ins_are_not_forwarded(self):
        assert garmin_push.weigh_ins([_group("2026-10-08T13:00:00", attrib=1)]) == []


class TestMissing:
    def test_a_weigh_in_garmin_already_has_is_not_sent_again(self):
        withings = garmin_push.weigh_ins([_group("2026-10-08T13:00:00", kg=80.0), _group("2026-10-09T13:00:00")])
        garmin = [(_at("2026-10-08T13:00:00") + timedelta(seconds=60), 80.03)]

        assert [w.at for w in garmin_push.missing(withings, garmin)] == [_at("2026-10-09T13:00:00")]

    def test_a_different_weight_at_the_same_time_is_still_missing(self):
        withings = garmin_push.weigh_ins([_group("2026-10-08T13:00:00", kg=80.0)])
        assert len(garmin_push.missing(withings, [(_at("2026-10-08T13:00:00"), 81.0)])) == 1


class TestFitFile:
    def test_timestamps_are_exact_whatever_the_process_timezone(self, monkeypatch):
        # garminconnect turns a datetime into seconds with time.mktime, which reads
        # it as LOCAL time; the push passes Unix seconds so the zone cannot matter.
        batch = garmin_push.weigh_ins([_group("2026-10-08T13:00:00"), _group("2026-10-09T13:30:00")])
        files = []
        for zone in ("UTC", "America/Los_Angeles", "Asia/Tokyo"):
            monkeypatch.setenv("TZ", zone)
            time.tzset()
            files.append(garmin_push.fit_file(batch, 183))
        monkeypatch.setenv("TZ", os.environ.get("TZ", "UTC"))
        time.tzset()

        assert files[0] == files[1] == files[2]
        for w in batch:
            assert struct.pack("<I", int(w.at.timestamp()) - FIT_EPOCH) in files[0]

    def test_bmi_uses_the_endurain_height(self):
        batch = garmin_push.weigh_ins([_group("2026-10-08T13:00:00", kg=80.0)])
        # 80 / 1.83^2 = 23.9, sent in tenths
        assert struct.pack("<H", 239) in garmin_push.fit_file(batch, 183)


def _garmin(existing=(), failures=None):
    client = MagicMock()
    client.garmin_connect_upload = "/upload-service/upload"
    client.get_weigh_ins.return_value = {
        "dailyWeightSummaries": [
            {"allWeightMetrics": [{"timestampGMT": int(at.timestamp() * 1000), "weight": kg * 1000}]}
            for at, kg in existing
        ]
    }
    response = MagicMock()
    response.json.return_value = {"detailedImportResult": {"successes": [{}], "failures": failures or []}}
    client.client.post.return_value = response
    return client


@pytest.fixture
def garmin_session():
    def install(client):
        return (
            patch.object(
                garmin_push.garmin_utils, "fetch_user_integrations_and_validate_token", return_value=MagicMock()
            ),
            patch.object(garmin_push.garmin_utils, "login_garminconnect_using_tokens", return_value=client),
        )

    return install


def _db(height=183):
    db = MagicMock()
    db.get.return_value = MagicMock(height=height)
    return db


GROUPS = [_group("2026-10-08T13:00:00", kg=80.0), _group("2026-10-09T13:00:00", kg=79.6)]
WINDOW = (date(2026, 10, 1), date(2026, 10, 25))


class TestPush:
    def test_uploads_only_what_garmin_lacks(self, garmin_session):
        client = _garmin(existing=[(_at("2026-10-08T13:00:00"), 80.0)])
        a, b = garmin_session(client)
        with a, b:
            counts, todo = garmin_push.push(1, GROUPS, *WINDOW, _db())

        assert [w.at for w in todo] == [_at("2026-10-09T13:00:00")]
        assert counts["uploaded"] == 1
        assert counts["already in garmin"] == 1
        assert client.client.post.call_count == 1

    def test_dry_run_and_limit_upload_nothing_or_less(self, garmin_session):
        client = _garmin()
        a, b = garmin_session(client)
        with a, b:
            counts, todo = garmin_push.push(1, GROUPS, *WINDOW, _db(), dry_run=True)
            assert counts["to upload"] == 2
            client.client.post.assert_not_called()
            counts, todo = garmin_push.push(1, GROUPS, *WINDOW, _db(), limit=1)

        assert counts["uploaded"] == 1
        assert [w.at for w in todo] == [_at("2026-10-08T13:00:00")]

    def test_a_refused_upload_raises(self, garmin_session):
        client = _garmin(failures=[{"messages": ["duplicate"]}])
        a, b = garmin_session(client)
        with a, b, pytest.raises(RuntimeError, match="refused"):
            garmin_push.push(1, GROUPS, *WINDOW, _db())

    def test_garmin_not_linked_uploads_nothing(self):
        with patch.object(garmin_push.garmin_utils, "fetch_user_integrations_and_validate_token", return_value=None):
            counts, todo = garmin_push.push(1, GROUPS, *WINDOW, _db())

        assert counts["garmin not linked"] == 1
        assert todo == []

    def test_large_backlogs_go_up_in_batches(self, garmin_session, monkeypatch):
        monkeypatch.setattr(garmin_push, "BATCH", 2)
        groups = [_group(f"2026-10-0{d}T13:00:00") for d in range(1, 6)]
        client = _garmin()
        a, b = garmin_session(client)
        with a, b:
            counts, _ = garmin_push.push(1, groups, *WINDOW, _db())

        assert counts["uploaded"] == 5
        assert client.client.post.call_count == 3


class TestSwitch:
    def test_off_unless_explicitly_true(self, monkeypatch):
        monkeypatch.delenv("WITHINGS_GARMIN_PUSH", raising=False)
        assert not garmin_push.enabled()
        monkeypatch.setenv("WITHINGS_GARMIN_PUSH", "true")
        assert garmin_push.enabled()
