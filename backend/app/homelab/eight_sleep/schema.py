"""API schemas for nightly HRV (homelab fork)."""

from datetime import date

from pydantic import BaseModel, ConfigDict


class SleepHrvRead(BaseModel):
    """One night's HRV, all values in ms as Eight Sleep reports them."""

    date: date
    hrv_ms: float
    avg_7d_ms: float | None
    baseline_ms: float | None
    range_low_ms: float | None
    range_high_ms: float | None
    source: str

    model_config = ConfigDict(from_attributes=True)


class SleepHrvListResponse(BaseModel):
    """A page of nights, newest first, with the total matching the filter."""

    total: int
    records: list[SleepHrvRead]
