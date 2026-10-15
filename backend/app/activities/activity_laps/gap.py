"""Grade-adjusted pace (GAP) for activity laps.

GAP is the pace a runner could hold on flat ground for the same effort. It
uses Strava's heart-rate-derived model (Robb, "An Improved GAP Model", Strava
Engineering, 2017). Strava has not published the model's coefficients, so this
uses a second-order fit to its published curve (Sci-DANI, "Mind the GAP"):

    a(g) = 1 + 0.02869556 * g + 0.001520768 * g**2   (g = grade in percent)

``a(g)`` is how much slower the hill pace is than the flat pace at equal
effort. A distance ``d`` run at grade ``g`` therefore counts as ``a(g) * d``
on the flat. The downhill benefit peaks near -9.4% (a ≈ 0.865), matching
Strava's note that it peaks around -10%.
"""

from collections.abc import Sequence
from datetime import datetime
from typing import Any

import numpy as np

# Activity types GAP applies to: running (1, 2, 3, 34, 40) and
# walking/hiking (11, 12, 31, 44).
GAP_ACTIVITY_TYPES: frozenset[int] = frozenset({1, 2, 3, 34, 40, 11, 12, 31, 44})

_COEF_LINEAR: float = 0.02869556
_COEF_QUADRATIC: float = 0.001520768

# The fit covers roughly ±30% grade; clamp to keep elevation noise and
# extrapolation from producing absurd factors.
_MAX_GRADE_PCT: float = 30.0

# Grade is measured over this horizontal distance, centred on each sample, to
# smooth elevation noise (GPS altitude especially).
_GRADE_WINDOW_M: float = 50.0

# A gap between samples longer than this is treated as a pause: it adds no
# distance, so auto-pause gaps do not create phantom distance.
_MAX_SAMPLE_GAP_S: float = 10.0

# Below this much stream distance, a lap's adjustment is too noisy to report.
_MIN_LAP_DISTANCE_M: float = 50.0


def grade_cost_factor(grade_pct: float) -> float:
    """
    Return the hill-to-flat pace factor for a grade.

    Args:
        grade_pct: Grade in percent (positive is uphill). Clamped to ±30%.

    Returns:
        Factor ``a(g)``: the hill pace divided by the equivalent flat pace.
    """
    g = max(-_MAX_GRADE_PCT, min(_MAX_GRADE_PCT, grade_pct))
    return 1.0 + _COEF_LINEAR * g + _COEF_QUADRATIC * g * g


def _to_seconds(value: Any) -> float | None:
    """
    Convert a waypoint ``time`` value to seconds.

    Strava streams store offsets in seconds; file imports store ISO 8601
    strings. Only differences between values are used, so the epoch does not
    matter as long as one stream uses one format.

    Args:
        value: Waypoint time (number of seconds or ISO 8601 string).

    Returns:
        Seconds as a float, or ``None`` when the value cannot be parsed.
    """
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


def _extract_series(waypoints: Sequence[dict], key: str) -> tuple[np.ndarray, np.ndarray]:
    """
    Extract ``(times, values)`` arrays from waypoints, sorted by time.

    Args:
        waypoints: Stream waypoints, each with ``time`` and ``key``.
        key: The value key (e.g. ``"vel"`` or ``"ele"``).

    Returns:
        Tuple of time and value arrays; empty when nothing is usable.
    """
    times: list[float] = []
    values: list[float] = []
    for waypoint in waypoints:
        seconds = _to_seconds(waypoint.get("time"))
        value = waypoint.get(key)
        if seconds is None or value is None:
            continue
        times.append(seconds)
        values.append(float(value))
    if not times:
        return np.array([]), np.array([])
    t = np.asarray(times)
    v = np.asarray(values)
    order = np.argsort(t, kind="stable")
    return t[order], v[order]


def _sample_grades(distance: np.ndarray, elevation: np.ndarray) -> np.ndarray:
    """
    Compute the grade (percent) at each sample over a centred distance window.

    Args:
        distance: Cumulative distance per sample (non-decreasing, metres).
        elevation: Elevation per sample (metres).

    Returns:
        Grade in percent per sample; ``0`` where no distance was covered.
    """
    # np.interp needs strictly increasing x; keep the first sample of each run
    # of equal distances (stopped samples).
    keep = np.concatenate(([True], np.diff(distance) > 0))
    xp = distance[keep]
    fp = elevation[keep]
    if xp.size < 2:
        return np.zeros_like(distance)

    half = _GRADE_WINDOW_M / 2
    lo = np.clip(distance - half, xp[0], xp[-1])
    hi = np.clip(distance + half, xp[0], xp[-1])
    span = hi - lo
    rise = np.interp(hi, xp, fp) - np.interp(lo, xp, fp)
    with np.errstate(divide="ignore", invalid="ignore"):
        grade = np.where(span > 0, rise / span * 100.0, 0.0)
    return np.clip(grade, -_MAX_GRADE_PCT, _MAX_GRADE_PCT)


def compute_laps_gap_ratio(
    laps: Sequence[tuple[datetime, float | None]],
    velocity_waypoints: Sequence[dict],
    elevation_waypoints: Sequence[dict],
) -> list[float | None]:
    """
    Compute each lap's grade-adjusted to actual distance ratio.

    Multiplying a lap's average speed by its ratio gives its grade-adjusted
    speed (dividing its pace gives GAP). Flat laps have a ratio of ~1.

    Lap windows are aligned to the streams using offsets from the first lap
    start and the first stream sample. This avoids the differences in how
    each import source stores lap and stream timestamps.

    Args:
        laps: ``(start_time, total_elapsed_time_seconds)`` per lap, in order.
        velocity_waypoints: Velocity stream waypoints (``time``, ``vel`` m/s).
        elevation_waypoints: Elevation stream waypoints (``time``, ``ele`` m).

    Returns:
        Ratio per lap, or ``None`` where the streams do not cover enough of it.
    """
    if not laps:
        return []

    vel_t, vel = _extract_series(velocity_waypoints, "vel")
    ele_t, ele = _extract_series(elevation_waypoints, "ele")
    if vel_t.size < 2 or ele_t.size < 2:
        return [None] * len(laps)

    # Distance covered since the previous sample (trapezoidal), skipping pauses.
    dt = np.diff(vel_t)
    step = np.where(
        (dt > 0) & (dt <= _MAX_SAMPLE_GAP_S),
        (np.maximum(vel[1:], 0) + np.maximum(vel[:-1], 0)) / 2 * dt,
        0.0,
    )
    step = np.concatenate(([0.0], step))
    distance = np.cumsum(step)

    elevation = np.interp(vel_t, ele_t, ele)
    grades = _sample_grades(distance, elevation)
    factors = 1.0 + _COEF_LINEAR * grades + _COEF_QUADRATIC * grades * grades
    adjusted = step * factors

    offsets = vel_t - vel_t[0]
    first_start = laps[0][0]
    ratios: list[float | None] = []
    for index, (start_time, elapsed) in enumerate(laps):
        start = (start_time - first_start).total_seconds()
        if index + 1 < len(laps):
            end = (laps[index + 1][0] - first_start).total_seconds()
        elif elapsed is not None:
            end = start + elapsed
        else:
            end = float(offsets[-1])
        # A sample's step covers the interval ending at it, so the window is
        # (start, end].
        in_lap = (offsets > start) & (offsets <= end)
        lap_distance = float(step[in_lap].sum())
        if lap_distance < _MIN_LAP_DISTANCE_M:
            ratios.append(None)
            continue
        ratios.append(float(adjusted[in_lap].sum()) / lap_distance)
    return ratios
