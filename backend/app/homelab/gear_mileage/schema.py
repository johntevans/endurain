"""Pydantic schemas for gear mileage."""

from pydantic import BaseModel, ConfigDict, Field


class GearMileageRead(BaseModel):
    """One gear's total distance."""

    model_config = ConfigDict(extra="forbid")

    gear_id: int = Field(..., description="Gear ID")
    total_distance: float = Field(
        ...,
        ge=0,
        description="Meters: its activities plus its initial distance, as on the gear page",
    )
