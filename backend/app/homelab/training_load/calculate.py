"""Intervals.icu-style training load, computed from an activity's streams.

Intervals.icu publishes no specification; these rules are the developer's
forum posts, checked against the owner's own Intervals.icu values (23 runs
and 9 strength/prehab sessions, September to October 2026: runs within ±1 but
one, HR loads 8 of 9 exact).

- **Pace load** (runs): ``timer_hours * (gap_speed / threshold_speed)**2 * 100``.
  GAP speed is the grade-adjusted distance over the moving samples divided by
  their time (Strava's model, ``activities.activity_laps.gap``). The time is
  the activity's timer time, not the moving time: Intervals counts standing
  with the timer running (a 5k time-trial day with 3 minutes stopped only
  matches that way).
- **HR load** (HRSS, a normalised TRIMP): every second weighted by Banister's
  ``x · a · e^(b·x)`` of its heart-rate reserve ``x``, divided by one hour at
  threshold HR, times 100. ``a, b`` are 0.64, 1.92 for men and 0.86, 1.67 for
  women. Summed per sample, never from the average HR.
- **Load** is the first of pace, HR that the activity has (Intervals' Run
  priority "Pace, HR, Power"; no FTP is set, so power never applies). Other
  sports use HR. Strength-type sessions get Load 0 and keep their HR load,
  as Intervals shows them.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

import numpy as np

from activities.activity_laps import gap

# Intervals' Run sport (Run, Trail Run, Virtual Run) plus Endurain's track run
# and treadmill.
PACE_ACTIVITY_TYPES: frozenset[int] = frozenset({1, 2, 3, 34, 40})

# Intervals shows these with Load 0 and the HR load in parentheses: workout,
# yoga, strength training and the fork's physical therapy (1001).
ZERO_LOAD_ACTIVITY_TYPES: frozenset[int] = frozenset({10, 14, 19, 1001})

# A sample slower than this is standing still: it adds neither distance nor
# time to the GAP speed.
MOVING_SPEED_MS: float = 0.5

# A gap between HR samples longer than this is a pause, not time at that HR.
_MAX_HR_SAMPLE_GAP_S: float = 30.0

_TRIMP_CONSTANTS = {"male": (0.64, 1.92), "female": (0.86, 1.67)}


class LoadSource(StrEnum):
    """Which calculation an activity's Load came from."""

    PACE = "pace"
    HR = "hr"
    NONE = "none"


@dataclass(frozen=True)
class Thresholds:
    """The athlete's settings the loads depend on."""

    resting_hr: float
    threshold_hr: float
    max_hr: float
    threshold_speed: float
    """Threshold pace as a speed, m/s."""
    gender: str = "male"


@dataclass(frozen=True)
class LoadResult:
    """One activity's loads. ``pace_load`` and ``hr_load`` are unrounded."""

    load: int
    source: LoadSource
    pace_load: float | None
    hr_load: float | None


def round_load(value: float) -> int:
    """Round half up, as Intervals displays loads (Python's ``round`` is half-even)."""
    return math.floor(value + 0.5)


def _seconds(value: Any) -> float | None:
    # File imports store ISO strings, Strava imports second offsets; only
    # differences are used, so the two epochs never mix within a stream.
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return None
    return None


def _trimp_weight(reserve: np.ndarray | float, gender: str) -> np.ndarray | float:
    a, b = _TRIMP_CONSTANTS.get(gender, _TRIMP_CONSTANTS["male"])
    return reserve * a * np.exp(b * reserve)


def hr_load(hr_waypoints: Sequence[dict], thresholds: Thresholds) -> float | None:
    """
    HRSS: the heart-rate load, 100 for one hour at threshold HR.

    Args:
        hr_waypoints: HR stream waypoints (``time``, ``hr`` bpm).
        thresholds: Resting, threshold and max HR.

    Returns:
        The load, or ``None`` with fewer than two HR samples or an unusable
        HR range.
    """
    span = thresholds.max_hr - thresholds.resting_hr
    if span <= 0:
        return None
    samples = sorted(
        (t, float(w["hr"]))
        for w in hr_waypoints
        if w.get("hr") is not None and (t := _seconds(w.get("time"))) is not None
    )
    if len(samples) < 2:
        return None
    times = np.array([t for t, _ in samples])
    bpm = np.array([hr for _, hr in samples])
    # Each sample's HR holds until the next sample.
    dt = np.diff(times)
    dt = np.where(dt <= _MAX_HR_SAMPLE_GAP_S, dt, 0.0)
    reserve = np.clip((bpm[:-1] - thresholds.resting_hr) / span, 0.0, 1.0)
    trimp = float((dt * _trimp_weight(reserve, thresholds.gender)).sum())
    threshold_reserve = (thresholds.threshold_hr - thresholds.resting_hr) / span
    hour_at_threshold = 3600 * float(_trimp_weight(threshold_reserve, thresholds.gender))
    if hour_at_threshold <= 0:
        return None
    return trimp / hour_at_threshold * 100


def gap_speed(velocity_waypoints: Sequence[dict], elevation_waypoints: Sequence[dict]) -> float | None:
    """
    Average grade-adjusted speed over the moving samples, m/s.

    Args:
        velocity_waypoints: Speed stream waypoints (``time``, ``vel`` m/s).
        elevation_waypoints: Elevation stream waypoints; empty means flat.

    Returns:
        The speed, or ``None`` when the activity never moved.
    """
    series = gap.gap_steps(velocity_waypoints, elevation_waypoints)
    if series is None:
        return None
    times, velocities, steps, factors = series
    dt = np.concatenate(([0.0], np.diff(times)))
    moving = (steps > 0) & (velocities >= MOVING_SPEED_MS)
    moving_time = float(dt[moving].sum())
    if moving_time <= 0:
        return None
    return float((steps * factors)[moving].sum()) / moving_time


def pace_load(speed: float, timer_seconds: float, thresholds: Thresholds) -> float | None:
    """
    Pace load from an average (grade-adjusted) speed: 100 for one hour at threshold pace.

    Args:
        speed: Average GAP speed, m/s.
        timer_seconds: The activity's timer time.
        thresholds: Threshold pace.

    Returns:
        The load, or ``None`` without a usable speed, time or threshold.
    """
    if speed <= 0 or timer_seconds <= 0 or thresholds.threshold_speed <= 0:
        return None
    intensity = speed / thresholds.threshold_speed
    return timer_seconds / 3600 * intensity * intensity * 100


def activity_load(
    activity_type: int,
    timer_seconds: float,
    distance_m: float,
    streams: dict[str, Sequence[dict]],
    thresholds: Thresholds,
) -> LoadResult:
    """
    Compute one activity's loads and pick its Load.

    Args:
        activity_type: Endurain activity type id.
        timer_seconds: Timer time (elapsed time when the activity has none).
        distance_m: Total distance, used for the pace when there is no speed stream.
        streams: Waypoints by key: ``hr``, ``vel`` and ``ele`` (any may be missing).
        thresholds: The athlete's settings.

    Returns:
        The loads; ``source`` is ``none`` (Load 0) when neither applies.
    """
    hr = hr_load(streams.get("hr", ()), thresholds)

    pace = None
    if activity_type in PACE_ACTIVITY_TYPES:
        speed = gap_speed(streams.get("vel", ()), streams.get("ele", ()))
        if speed is None and distance_m > 0 and timer_seconds > 0:
            speed = distance_m / timer_seconds
        if speed is not None:
            pace = pace_load(speed, timer_seconds, thresholds)

    if activity_type in ZERO_LOAD_ACTIVITY_TYPES:
        return LoadResult(load=0, source=LoadSource.NONE, pace_load=None, hr_load=hr)
    if pace is not None:
        return LoadResult(load=round_load(pace), source=LoadSource.PACE, pace_load=pace, hr_load=hr)
    if hr is not None:
        return LoadResult(load=round_load(hr), source=LoadSource.HR, pace_load=None, hr_load=hr)
    return LoadResult(load=0, source=LoadSource.NONE, pace_load=None, hr_load=None)
