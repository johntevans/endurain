"""Intervals.icu-style fitness, fatigue and form from daily training loads.

Fitness and fatigue are exponentially weighted averages of each day's load,
over 42 and 7 days: ``today = yesterday * e^(-1/days) + load * (1 - e^(-1/days))``,
the day's own load included. Form is fitness minus fatigue on the same day,
ramp the change in fitness over the last 7 days.

Checked against the owner's Intervals.icu weeks (2026-09-27 to 10-22):
fitness within 0.3 every week, fatigue about 0.5 low (the run loads' own
slight low bias). The fit needs one more rule, from the owner's Intervals
settings: workout, strength and physical therapy (Intervals' "Weight
Training") add their HR load to fatigue only, and yoga adds nothing.
"""

import math
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta

FITNESS_DAYS = 42
FATIGUE_DAYS = 7
RAMP_DAYS = 7

# Share of the HR load that counts toward (fitness, fatigue), for activity
# types whose Load is 0 (``calculate.ZERO_LOAD_ACTIVITY_TYPES``). Every other
# activity counts its Load toward both.
HR_LOAD_SHARES: dict[int, tuple[float, float]] = {
    10: (0.0, 1.0),  # workout
    14: (0.0, 0.0),  # yoga
    19: (0.0, 1.0),  # strength training
    1001: (0.0, 1.0),  # physical therapy (homelab fork)
}


@dataclass(frozen=True)
class ActivityInput:
    """What one activity contributes to its local day."""

    local_date: date
    activity_type: int
    load: int
    hr_load: float | None


@dataclass
class DayInput:
    """One day's summed loads."""

    load: float = 0.0
    """The Loads shown on the day's activities."""
    fitness: float = 0.0
    fatigue: float = 0.0


@dataclass(frozen=True)
class FitnessDay:
    """Fitness, fatigue and form at the end of one local day."""

    day: date
    load: float
    fitness: float
    fatigue: float
    form: float
    ramp: float


def daily_inputs(activities: Iterable[ActivityInput]) -> dict[date, DayInput]:
    """Sum each day's contributions to fitness and fatigue."""
    days: dict[date, DayInput] = {}
    for activity in activities:
        day = days.setdefault(activity.local_date, DayInput())
        day.load += activity.load
        shares = HR_LOAD_SHARES.get(activity.activity_type)
        if shares is None:
            day.fitness += activity.load
            day.fatigue += activity.load
        elif activity.hr_load is not None:
            day.fitness += activity.hr_load * shares[0]
            day.fatigue += activity.hr_load * shares[1]
    return days


def fitness_series(inputs: dict[date, DayInput], start: date, first: date, last: date) -> list[FitnessDay]:
    """
    Run the averages from ``start`` (both 0 the day before) and return ``first``..``last``.

    Args:
        inputs: Day inputs by local date (days without activities may be missing).
        start: First day of the loads; the averages start from zero there.
        first: First day to return (not before ``start``).
        last: Last day to return; days after the last activity decay toward 0.

    Returns:
        One entry per day, in order.
    """
    fitness_keep = math.exp(-1 / FITNESS_DAYS)
    fatigue_keep = math.exp(-1 / FATIGUE_DAYS)
    fitness = fatigue = 0.0
    history: list[float] = []
    result: list[FitnessDay] = []
    day = start
    while day <= last:
        today = inputs.get(day) or DayInput()
        fitness = fitness * fitness_keep + today.fitness * (1 - fitness_keep)
        fatigue = fatigue * fatigue_keep + today.fatigue * (1 - fatigue_keep)
        history.append(fitness)
        week_ago = history[-RAMP_DAYS - 1] if len(history) > RAMP_DAYS else 0.0
        if day >= first:
            result.append(
                FitnessDay(
                    day=day,
                    load=today.load,
                    fitness=fitness,
                    fatigue=fatigue,
                    form=fitness - fatigue,
                    ramp=fitness - week_ago,
                )
            )
        day += timedelta(days=1)
    return result
