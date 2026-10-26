"""Withings measurement groups -> Endurain ``health_weight`` rows.

One row per local date: the day's FIRST weigh-in, usually the morning,
pre-food weight and so the most comparable day to day (decided 2026-10-23).
Body composition comes from that same group, never mixed across groups.

Skipped: groups Withings marks ``attrib`` 1, "measured but ambiguous" (the
scale was not sure whose weight it was, e.g. a guest). Hand entries in the
Withings app (``attrib`` 2) are kept; they are the owner's own data.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import health.health_weight.schema as health_weight_schema

AMBIGUOUS_ATTRIBS = frozenset({1})

WEIGHT, FAT_RATIO, MUSCLE_MASS, HYDRATION, BONE_MASS, VISCERAL_FAT = 1, 6, 76, 77, 88, 170


@dataclass
class DayWeight:
    date: date
    weight: health_weight_schema.HealthWeightBase
    measured_at: datetime


def _values(group: dict[str, Any]) -> dict[int, float]:
    # Withings encodes each value as value * 10^unit.
    out = {}
    for measure in group.get("measures") or []:
        try:
            out[int(measure["type"])] = float(measure["value"]) * 10 ** int(measure["unit"])
        except (KeyError, TypeError, ValueError):
            continue
    return out


def _bounded(value: float | None, high: float) -> float | None:
    if value is None or not 0 <= value <= high:
        return None
    return round(value, 2)


def map_groups(groups: list[dict[str, Any]], tz_name: str) -> tuple[dict[date, DayWeight], int]:
    """
    The first weigh-in of each local day.

    Returns:
        ``(by_date, skipped_ambiguous)``.
    """
    tz = ZoneInfo(tz_name)
    by_date: dict[date, DayWeight] = {}
    skipped = 0
    for group in groups:
        if group.get("attrib") in AMBIGUOUS_ATTRIBS:
            skipped += 1
            continue
        values = _values(group)
        weight = values.get(WEIGHT)
        if weight is None or not 0 < weight <= 500:
            continue
        measured_at = datetime.fromtimestamp(int(group["date"]), UTC)
        day = measured_at.astimezone(tz).date()
        if day in by_date and by_date[day].measured_at <= measured_at:
            continue
        hydration = values.get(HYDRATION)
        by_date[day] = DayWeight(
            date=day,
            measured_at=measured_at,
            weight=health_weight_schema.HealthWeightBase(
                date=day,
                weight=round(weight, 2),
                body_fat=_bounded(values.get(FAT_RATIO), 100),
                # Endurain stores body water as a percentage of weight; Withings sends kg.
                body_water=_bounded(hydration / weight * 100 if hydration is not None else None, 100),
                bone_mass=_bounded(values.get(BONE_MASS), 500),
                muscle_mass=_bounded(values.get(MUSCLE_MASS), 500),
                visceral_fat=_bounded(values.get(VISCERAL_FAT), 100),
                source=health_weight_schema.Source.WITHINGS,
            ),
        )
    return by_date, skipped
