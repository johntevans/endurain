"""Pydantic schemas for training load."""

from pydantic import BaseModel, ConfigDict, Field

from homelab.training_load.calculate import LoadSource, round_load
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
