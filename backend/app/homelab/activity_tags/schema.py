"""Pydantic schemas for activity tags."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ActivityTagKey(StrEnum):
    """The fixed set of activity tags, as stored.

    Keys are stable identifiers; labels are the frontend's job. The first
    three match Strava's run ``workout_type`` (1 race, 2 long run, 3 workout)
    so a later Strava-sourced value can be compared against the user's own
    tags without a mapping table. The ``nsm_*`` tags mark Norwegian Singles
    Method sub-threshold sessions by rep length: short 2-4 min, medium
    5-7 min, long 8 min and up.

    Adding a key also needs a fork migration widening the table's CHECK
    constraint (see ``hl0002_nsm_activity_tags``).
    """

    RACE = "race"
    WORKOUT = "workout"
    LONG_RUN = "long_run"
    NSM_SHORT = "nsm_short"
    NSM_MEDIUM = "nsm_medium"
    NSM_LONG = "nsm_long"


TAG_ORDER: dict[str, int] = {tag.value: index for index, tag in enumerate(ActivityTagKey)}


def sort_tags(tags: list[str] | set[str]) -> list[ActivityTagKey]:
    """Return unique tags in canonical order (``ActivityTagKey`` definition order)."""
    return [ActivityTagKey(tag) for tag in sorted(set(tags), key=TAG_ORDER.__getitem__)]


class ActivityTagsRead(BaseModel):
    """Tags of one activity."""

    activity_id: int = Field(..., description="Activity ID")
    tags: list[ActivityTagKey] = Field(default_factory=list, description="Tags, in canonical order")

    model_config = ConfigDict(extra="forbid")


class ActivityTagsUpdate(BaseModel):
    """The complete new tag set for an activity (replaces the old one)."""

    tags: list[ActivityTagKey] = Field(
        ...,
        max_length=len(ActivityTagKey),
        description="Up to one of each tag; duplicates are ignored",
    )

    model_config = ConfigDict(extra="forbid")
