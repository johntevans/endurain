"""Pydantic schemas and rules for lap intensity."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from homelab.activity_tags.schema import ActivityTagKey


class LapIntensityKey(StrEnum):
    """The FIT ``intensity`` values a lap can be given.

    Upstream stores whatever the file says in ``activity_laps.intensity`` (or
    nothing: GPX, TCX and Strava imports leave it empty). An override must be
    one of these.
    """

    ACTIVE = "active"
    INTERVAL = "interval"
    WARMUP = "warmup"
    COOLDOWN = "cooldown"
    RECOVERY = "recovery"
    REST = "rest"
    OTHER = "other"


# What a lap of an ordinary, unstructured run is: FIT's default intensity.
# Laps with no recorded intensity read as this until overridden.
DEFAULT_INTENSITY = LapIntensityKey.ACTIVE

# The work portions of a session. Structured workouts mark their reps
# ``active``; newer Garmin watches mark every lap of a free run ``interval``.
QUALITY_INTENSITIES: frozenset[str] = frozenset({LapIntensityKey.ACTIVE, LapIntensityKey.INTERVAL})

# Only activities with one of these tags have quality laps. A long run is not
# a quality session on its own (it is when it is also tagged workout).
QUALITY_TAGS: frozenset[str] = frozenset(
    {
        ActivityTagKey.RACE,
        ActivityTagKey.WORKOUT,
        ActivityTagKey.NSM_SHORT,
        ActivityTagKey.NSM_MEDIUM,
        ActivityTagKey.NSM_LONG,
    }
)


class LapIntensitySource(StrEnum):
    """Where a lap's effective intensity comes from."""

    RECORDED = "recorded"
    DEFAULT = "default"
    OVERRIDE = "override"


class LapIntensityRead(BaseModel):
    """One lap's effective intensity and where it comes from."""

    lap_id: int = Field(..., description="Lap ID")
    intensity: str = Field(
        ..., description="Effective intensity: the override, else the recorded value, else the default"
    )
    recorded: str | None = Field(default=None, description="Intensity as recorded in the activity file")
    source: LapIntensitySource = Field(..., description="Which of override, recorded or default applies")

    model_config = ConfigDict(extra="forbid")


class LapIntensityUpdate(BaseModel):
    """A lap's new override; ``null`` removes it (back to recorded or default)."""

    intensity: LapIntensityKey | None = Field(..., description="Override, or null to clear it")

    model_config = ConfigDict(extra="forbid")


def effective_intensity(override: str | None, recorded: str | None) -> tuple[str, LapIntensitySource]:
    """Resolve a lap's intensity: override, else recorded, else the default."""
    if override:
        return override, LapIntensitySource.OVERRIDE
    if recorded:
        return recorded, LapIntensitySource.RECORDED
    return DEFAULT_INTENSITY.value, LapIntensitySource.DEFAULT
