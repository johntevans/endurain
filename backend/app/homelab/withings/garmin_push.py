"""Forward Withings weigh-ins on to Garmin Connect (homelab fork).

Garmin itself is the record of what is already there, so no state is kept:
each run lists Garmin's weigh-ins for the window and uploads only the Withings
weigh-ins it does not have. Measured 2026-10-26, Garmin already held 364 of
the 434 Withings weigh-ins at the identical second and weight (from an earlier
forwarder that stopped in January 2026), so a match is "within
``MATCH_SECONDS`` and ``MATCH_KG``". Garmin-only weigh-ins (manual entries)
are never touched, and nothing is ever deleted from Garmin.

Uploads are a FIT weight file through the session Endurain already holds for
the Garmin activity sync, so there is no second Garmin login from the home IP
(repeated logins got 429s in October 2026). Every weigh-in carries what the
earlier forwarder sent (weight, BMI, body fat %, water %, bone, muscle) plus
Withings' visceral fat index.

**Timestamps are passed as Unix seconds, never as datetimes**: garminconnect's
``FitEncoder.timestamp`` turns a datetime into seconds with ``time.mktime``,
which ignores tzinfo and reads it as the container's local time, so a UTC
datetime would land 7-8 hours off.

Off unless ``WITHINGS_GARMIN_PUSH=true``.
"""

import os
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from garminconnect.fit import FitEncoderWeight
from sqlalchemy.orm import Session

import garmin.utils as garmin_utils
import users.users.models as users_models
from homelab.withings import mapping as withings_mapping

MATCH_SECONDS = 120
MATCH_KG = 0.06
# Weigh-ins per uploaded FIT file.
BATCH = 50


def enabled() -> bool:
    return os.environ.get("WITHINGS_GARMIN_PUSH", "").strip().lower() == "true"


@dataclass(frozen=True)
class WeighIn:
    """One Withings weigh-in in the units the FIT weight message wants."""

    at: datetime
    weight: float
    percent_fat: float | None
    percent_hydration: float | None
    bone_mass: float | None
    muscle_mass: float | None
    visceral_fat_rating: float | None


def weigh_ins(groups: list[dict[str, Any]]) -> list[WeighIn]:
    """Every usable Withings weigh-in (not only the first of the day), oldest first."""
    out = []
    for group in groups:
        if group.get("attrib") in withings_mapping.AMBIGUOUS_ATTRIBS:
            continue
        values = withings_mapping._values(group)
        weight = values.get(withings_mapping.WEIGHT)
        if weight is None or not 0 < weight <= 500:
            continue
        hydration = values.get(withings_mapping.HYDRATION)

        def r2(value):
            # Withings sends value * 10^unit, so 330e-2 arrives as 3.3000000000000003.
            return round(value, 2) if value is not None else None

        out.append(
            WeighIn(
                at=datetime.fromtimestamp(int(group["date"]), UTC),
                weight=round(weight, 2),
                percent_fat=r2(values.get(withings_mapping.FAT_RATIO)),
                percent_hydration=r2(hydration / weight * 100 if hydration is not None else None),
                bone_mass=r2(values.get(withings_mapping.BONE_MASS)),
                muscle_mass=r2(values.get(withings_mapping.MUSCLE_MASS)),
                # Garmin keeps a whole-number rating and the FIT field is a uint8, which
                # truncates: Withings' 2.6 arrived as 2 on 2026-10-26 until this rounding.
                visceral_fat_rating=(
                    round(values[withings_mapping.VISCERAL_FAT])
                    if values.get(withings_mapping.VISCERAL_FAT) is not None
                    else None
                ),
            )
        )
    return sorted(out, key=lambda w: w.at)


def garmin_weigh_ins(garmin_client: Any, start: date, end: date) -> list[tuple[datetime, float]]:
    """``(time, kg)`` of every weigh-in Garmin holds between two calendar dates."""
    payload = garmin_client.get_weigh_ins(start.isoformat(), end.isoformat()) or {}
    out = []
    for summary in payload.get("dailyWeightSummaries") or []:
        for metric in summary.get("allWeightMetrics") or []:
            if metric.get("timestampGMT") and metric.get("weight"):
                out.append((datetime.fromtimestamp(metric["timestampGMT"] / 1000, UTC), metric["weight"] / 1000))
    return out


def missing(withings: list[WeighIn], garmin: list[tuple[datetime, float]]) -> list[WeighIn]:
    """The Withings weigh-ins Garmin does not already have."""
    return [
        w
        for w in withings
        if not any(
            abs((at - w.at).total_seconds()) <= MATCH_SECONDS and abs(kg - w.weight) < MATCH_KG for at, kg in garmin
        )
    ]


def fit_file(batch: list[WeighIn], height_cm: int | None) -> bytes:
    """A FIT weight file holding every weigh-in in ``batch``."""
    encoder = FitEncoderWeight()
    encoder.write_file_info(time_created=batch[0].at.timestamp())
    encoder.write_file_creator()
    encoder.write_device_info(batch[0].at.timestamp())
    for w in batch:
        bmi = round(w.weight / (height_cm / 100) ** 2, 1) if height_cm else None
        encoder.write_weight_scale(
            w.at.timestamp(),
            weight=w.weight,
            percent_fat=w.percent_fat,
            percent_hydration=w.percent_hydration,
            bone_mass=w.bone_mass,
            muscle_mass=w.muscle_mass,
            visceral_fat_rating=w.visceral_fat_rating,
            bmi=bmi,
        )
    encoder.finish()
    return encoder.getvalue()


def upload(garmin_client: Any, data: bytes) -> None:
    """Post one FIT file; raise unless Garmin reports it accepted."""
    response = garmin_client.client.post(
        "connectapi",
        garmin_client.garmin_connect_upload,
        files={"file": ("withings.fit", data)},
        api=True,
    )
    body = response.json() if hasattr(response, "json") else response
    result = (body or {}).get("detailedImportResult") or {}
    if result.get("failures"):
        raise RuntimeError(f"Garmin refused the upload: {result['failures'][:1]}")


def push(
    user_id: int,
    groups: list[dict[str, Any]],
    start: date,
    end: date,
    db: Session,
    *,
    limit: int | None = None,
    dry_run: bool = False,
) -> tuple[Counter, list[WeighIn]]:
    """
    Upload the Withings weigh-ins in ``start..end`` that Garmin lacks.

    Returns:
        ``(counts, missing)``; ``missing`` is what was (or, dry-run, would be) uploaded.

    Raises:
        Anything from Garmin; the caller logs it, and the next run retries,
        because nothing is recorded locally.
    """
    counts: Counter = Counter()
    integrations = garmin_utils.fetch_user_integrations_and_validate_token(user_id, db)
    if integrations is None:
        counts["garmin not linked"] += 1
        return counts, []
    garmin_client = garmin_utils.login_garminconnect_using_tokens(integrations.garminconnect_token)
    withings = [w for w in weigh_ins(groups) if start <= w.at.date() <= end + timedelta(days=1)]
    # A day of margin either side: Garmin files by local date, these are UTC.
    garmin = garmin_weigh_ins(garmin_client, start - timedelta(days=1), end + timedelta(days=1))
    todo = missing(withings, garmin)
    counts["already in garmin"] = len(withings) - len(todo)
    if limit is not None:
        todo = todo[:limit]
    if dry_run or not todo:
        counts["to upload"] = len(todo)
        return counts, todo
    user = db.get(users_models.Users, user_id)
    height = user.height if user is not None else None
    for i in range(0, len(todo), BATCH):
        upload(garmin_client, fit_file(todo[i : i + BATCH], height))
        counts["uploaded"] += len(todo[i : i + BATCH])
    return counts, todo
