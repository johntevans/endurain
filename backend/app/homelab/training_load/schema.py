"""Pydantic schemas for training load."""

import datetime

from pydantic import BaseModel, ConfigDict, Field

from homelab.training_load.calculate import LoadSource, round_load
from homelab.training_load.fitness import FitnessDay
from homelab.training_load.models import ActivityLoad


class ActivityLoadRead(BaseModel):
    """One activity's training load, as Intervals.icu would show it.

    Every value is ``None`` when the activity has no load: its owner has set
    no thresholds, or it predates the loads' start date.
    """

    activity_id: int = Field(..., description="Activity ID")
    load: int | None = Field(default=None, description="Training load (pace, else HR; 0 for strength)")
    source: LoadSource | None = Field(default=None, description="Which load the training load is")
    pace_load: int | None = Field(default=None, description="Pace load (runs)")
    hr_load: int | None = Field(default=None, description="Heart-rate load (HRSS)")

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def from_row(cls, activity_id: int, row: ActivityLoad | None) -> "ActivityLoadRead":
        """Build from a stored row (or its absence)."""
        if row is None:
            return cls(activity_id=activity_id)
        return cls(
            activity_id=activity_id,
            load=row.load,
            source=LoadSource(row.source),
            pace_load=round_load(row.pace_load) if row.pace_load is not None else None,
            hr_load=round_load(row.hr_load) if row.hr_load is not None else None,
        )


class FitnessDayRead(BaseModel):
    """Fitness, fatigue and form at the end of one local day, to one decimal."""

    date: datetime.date = Field(..., description="Local date")
    load: int = Field(..., ge=0, description="Sum of the day's activity loads")
    fitness: float = Field(..., description="42-day exponentially weighted load (Intervals' Fitness)")
    fatigue: float = Field(..., description="7-day exponentially weighted load (Intervals' Fatigue)")
    form: float = Field(..., description="Fitness minus fatigue")
    ramp: float = Field(..., description="Change in fitness over the last 7 days")

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def from_day(cls, day: FitnessDay) -> "FitnessDayRead":
        """Build from a computed day, rounded for display."""
        return cls(
            date=day.day,
            load=round_load(day.load),
            fitness=round(day.fitness, 1),
            fatigue=round(day.fatigue, 1),
            form=round(day.form, 1),
            ramp=round(day.ramp, 1),
        )


class FitnessRead(BaseModel):
    """A user's daily fitness, fatigue and form over a range of local dates."""

    loads_start: datetime.date = Field(..., description="First date with loads; the averages start from zero there")
    has_settings: bool = Field(..., description="Whether the user has set thresholds (no days otherwise)")
    days: list[FitnessDayRead] = Field(default_factory=list, description="One entry per day, oldest first")

    model_config = ConfigDict(extra="forbid")
