"""Pydantic schemas for the training log."""

from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from homelab.activity_tags.schema import ActivityTagKey


class TrainingLogActivity(BaseModel):
    """One activity, trimmed to what a training-log circle needs.

    Dates are the activity's own local calendar date (its ``timezone``, or the
    server's when it has none), so a 6 am run in Tokyo lands on the day it was
    run rather than the UTC day.
    """

    id: int = Field(..., description="Activity ID")
    name: str = Field(..., description="Activity name")
    activity_type: int = Field(..., description="Numeric activity type code")
    local_date: date = Field(..., description="Local calendar date the activity started on")
    start_time: str = Field(..., description="Local start time, ISO 8601 without offset")
    distance: int = Field(..., ge=0, description="Distance in meters")
    total_timer_time: float = Field(..., ge=0, description="Moving (timer) time in seconds")
    total_elapsed_time: float = Field(..., ge=0, description="Elapsed time in seconds")
    elevation_gain: int | None = Field(default=None, description="Elevation gain in meters")
    tags: list[ActivityTagKey] = Field(default_factory=list, description="Activity tags, in canonical order")
    quality_time: float = Field(
        default=0,
        ge=0,
        description="Seconds in quality laps (active or interval) of a race, workout or NSM session; 0 otherwise",
    )
    quality_distance: float = Field(
        default=0,
        ge=0,
        description="Metres in quality laps of a race, workout or NSM session; 0 otherwise",
    )

    model_config = ConfigDict(extra="forbid")


class TrainingLogRange(BaseModel):
    """Local dates of the user's first and last (non-hidden) activity."""

    first_date: date | None = Field(default=None, description="Local date of the first activity")
    last_date: date | None = Field(default=None, description="Local date of the most recent activity")

    model_config = ConfigDict(extra="forbid")
