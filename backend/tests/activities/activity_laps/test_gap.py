from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

import activities.activity_laps.crud as crud
import activities.activity_laps.gap as gap
import activities.activity_laps.schema as schema
import activities.activity_streams.constants as stream_constants

_START = datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC)


def _streams(seconds: int, speed: float, grade_pct: float, iso: bool = True):
    """Build 1 Hz velocity/elevation waypoints at a constant speed and grade."""
    vel, ele = [], []
    for i in range(seconds + 1):
        t = (_START + timedelta(seconds=i)).strftime("%Y-%m-%dT%H:%M:%S") if iso else i
        vel.append({"time": t, "vel": speed})
        ele.append({"time": t, "ele": 100 + speed * i * grade_pct / 100})
    return vel, ele


class TestGradeCostFactor:
    def test_flat_is_one(self):
        assert gap.grade_cost_factor(0) == 1

    def test_uphill_is_slower(self):
        assert gap.grade_cost_factor(10) == pytest.approx(1.4390, abs=1e-4)

    def test_downhill_benefit_peaks_near_minus_ten(self):
        factors = {g: gap.grade_cost_factor(g) for g in range(-20, 1)}
        best = min(factors, key=factors.get)
        assert best in (-9, -10)
        assert factors[best] == pytest.approx(0.865, abs=0.002)

    def test_clamped(self):
        assert gap.grade_cost_factor(60) == gap.grade_cost_factor(30)
        assert gap.grade_cost_factor(-60) == gap.grade_cost_factor(-30)


class TestComputeLapsGapRatio:
    def test_flat_ratio_is_one(self):
        vel, ele = _streams(600, 3.0, 0)
        ratios = gap.compute_laps_gap_ratio([(_START, 600.0)], vel, ele)
        assert ratios[0] == pytest.approx(1.0)

    def test_constant_uphill(self):
        vel, ele = _streams(600, 3.0, 5)
        ratios = gap.compute_laps_gap_ratio([(_START, 600.0)], vel, ele)
        assert ratios[0] == pytest.approx(gap.grade_cost_factor(5), rel=1e-3)

    def test_constant_downhill_with_strava_offsets(self):
        vel, ele = _streams(600, 3.0, -8, iso=False)
        ratios = gap.compute_laps_gap_ratio([(_START, 600.0)], vel, ele)
        assert ratios[0] == pytest.approx(gap.grade_cost_factor(-8), rel=1e-3)

    def test_splits_by_lap(self):
        flat_vel, flat_ele = _streams(300, 3.0, 0)
        # Continue with a 6% climb from where the flat section ends.
        climb_vel, climb_ele = [], []
        for i in range(1, 301):
            t = (_START + timedelta(seconds=300 + i)).strftime("%Y-%m-%dT%H:%M:%S")
            climb_vel.append({"time": t, "vel": 3.0})
            climb_ele.append({"time": t, "ele": 100 + 3.0 * i * 0.06})
        laps = [(_START, 300.0), (_START + timedelta(seconds=300), 300.0)]
        ratios = gap.compute_laps_gap_ratio(laps, flat_vel + climb_vel, flat_ele + climb_ele)
        assert ratios[0] == pytest.approx(1.0, abs=0.02)
        assert ratios[1] == pytest.approx(gap.grade_cost_factor(6), abs=0.02)

    def test_pause_adds_no_distance(self):
        vel, ele = _streams(120, 3.0, 0)
        late = (_START + timedelta(seconds=600)).strftime("%Y-%m-%dT%H:%M:%S")
        vel.append({"time": late, "vel": 3.0})
        ele.append({"time": late, "ele": 100})
        # The second lap only spans the pause, so it has too little distance.
        laps = [(_START, 120.0), (_START + timedelta(seconds=120), 480.0)]
        ratios = gap.compute_laps_gap_ratio(laps, vel, ele)
        assert ratios[0] == pytest.approx(1.0)
        assert ratios[1] is None

    def test_missing_streams(self):
        vel, _ = _streams(600, 3.0, 0)
        assert gap.compute_laps_gap_ratio([(_START, 600.0)], vel, []) == [None]
        assert gap.compute_laps_gap_ratio([], vel, []) == []

    def test_ignores_unparseable_times(self):
        vel, ele = _streams(600, 3.0, 0)
        vel.append({"time": "not-a-time", "vel": 3.0})
        ele.append({"time": None, "ele": 500})
        ratios = gap.compute_laps_gap_ratio([(_START, 600.0)], vel, ele)
        assert ratios[0] == pytest.approx(1.0)


def _lap(lap_id: int, offset_s: int, elapsed: float, speed: float | None) -> schema.ActivityLapsRead:
    return schema.ActivityLapsRead(
        id=lap_id,
        activity_id=1,
        start_time=_START + timedelta(seconds=offset_s),
        total_elapsed_time=elapsed,
        enhanced_avg_speed=speed,
        enhanced_avg_pace=None if speed is None else 1 / speed,
    )


def _stream(stream_type: int, waypoints: list[dict]) -> MagicMock:
    return MagicMock(stream_type=stream_type, stream_waypoints=waypoints)


class TestAttachGradeAdjustedPace:
    def _db(self, vel, ele):
        db = MagicMock()
        db.scalars.return_value.all.return_value = [
            _stream(stream_constants.STREAM_TYPE_SPEED, vel),
            _stream(stream_constants.STREAM_TYPE_ELEVATION, ele),
        ]
        return db

    def _activity(self, **overrides):
        values = {
            "id": 1,
            "user_id": 1,
            "activity_type": 1,
            "hide_elevation": False,
            "hide_speed": False,
            "hide_pace": False,
        }
        values.update(overrides)
        return MagicMock(**values)

    def test_sets_gap_on_uphill_run(self):
        vel, ele = _streams(600, 3.0, 5)
        laps = [_lap(1, 0, 600.0, 3.0)]
        crud._attach_grade_adjusted_pace(laps, self._activity(), 1, self._db(vel, ele))
        expected_speed = 3.0 * gap.grade_cost_factor(5)
        assert laps[0].grade_adjusted_avg_speed == pytest.approx(expected_speed, rel=1e-3)
        assert laps[0].grade_adjusted_avg_pace == pytest.approx(1 / expected_speed, rel=1e-3)

    def test_unordered_laps(self):
        vel, ele = _streams(600, 3.0, 0)
        laps = [_lap(2, 300, 300.0, 3.0), _lap(1, 0, 300.0, 3.0)]
        crud._attach_grade_adjusted_pace(laps, self._activity(), 1, self._db(vel, ele))
        assert all(lap.grade_adjusted_avg_speed == pytest.approx(3.0) for lap in laps)

    def test_skips_non_running(self):
        vel, ele = _streams(600, 3.0, 5)
        laps = [_lap(1, 0, 600.0, 3.0)]
        db = self._db(vel, ele)
        crud._attach_grade_adjusted_pace(laps, self._activity(activity_type=4), 1, db)
        assert laps[0].grade_adjusted_avg_speed is None
        db.scalars.assert_not_called()

    @pytest.mark.parametrize("hidden", ["hide_elevation", "hide_speed", "hide_pace"])
    def test_skips_hidden_for_non_owner(self, hidden):
        vel, ele = _streams(600, 3.0, 5)
        laps = [_lap(1, 0, 600.0, 3.0)]
        db = self._db(vel, ele)
        crud._attach_grade_adjusted_pace(laps, self._activity(**{hidden: True}), None, db)
        assert laps[0].grade_adjusted_avg_speed is None
        db.scalars.assert_not_called()

    def test_owner_sees_gap_despite_privacy(self):
        vel, ele = _streams(600, 3.0, 5)
        laps = [_lap(1, 0, 600.0, 3.0)]
        crud._attach_grade_adjusted_pace(laps, self._activity(hide_pace=True), 1, self._db(vel, ele))
        assert laps[0].grade_adjusted_avg_speed is not None

    def test_missing_elevation_stream(self):
        vel, _ = _streams(600, 3.0, 5)
        laps = [_lap(1, 0, 600.0, 3.0)]
        db = MagicMock()
        db.scalars.return_value.all.return_value = [_stream(stream_constants.STREAM_TYPE_SPEED, vel)]
        crud._attach_grade_adjusted_pace(laps, self._activity(), 1, db)
        assert laps[0].grade_adjusted_avg_speed is None

    def test_lap_without_speed(self):
        vel, ele = _streams(600, 3.0, 5)
        laps = [_lap(1, 0, 600.0, None)]
        crud._attach_grade_adjusted_pace(laps, self._activity(), 1, self._db(vel, ele))
        assert laps[0].grade_adjusted_avg_speed is None
