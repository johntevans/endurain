"""Eight Sleep day record -> Endurain ``health_sleep`` row.

One Endurain row per date, from the day's MAIN session only. Eight Sleep's own
day totals (score, sleep and stage durations) already cover just that session,
so a second session on the same day never leaks into them.

What is skipped, and why:

- **Daytime sessions.** A day whose main session starts between 06:00 and
  18:00 local is not imported. On days with no overnight session Eight Sleep
  promotes whatever else it recorded to "main"; in October 2026 those were
  someone or something else on the bed (avg HR ~75 against a ~47 baseline,
  breathing ~13/min against ~17), scoring 28-31. The cost is that a genuine
  afternoon nap or jet-lagged sleep is skipped too.
- **Sessions still processing** (``processing: true``, i.e. today's, in bed or
  just up). Picked up by a later run once final.
"""

import statistics
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from enum import Enum
from typing import Any
from zoneinfo import ZoneInfo

import health.health_sleep.schema as health_sleep_schema
import health.health_sleep.sleep_scoring as health_sleep_scoring

DAYTIME_START_HOUR = 6
DAYTIME_END_HOUR = 18

_STAGES = {
    "awake": health_sleep_schema.SleepStageType.AWAKE,
    "light": health_sleep_schema.SleepStageType.LIGHT,
    "deep": health_sleep_schema.SleepStageType.DEEP,
    "rem": health_sleep_schema.SleepStageType.REM,
    # "out" (out of bed) has no Endurain stage: it advances the clock only.
}


class Skip(Enum):
    """Why a day produced no row."""

    NO_MAIN_SESSION = "no main session"
    PROCESSING = "still processing"
    DAYTIME = "daytime session"
    NO_SLEEP = "no sleep recorded"


@dataclass
class HrvNight:
    """Eight Sleep's HRV block for one night (``sleepQualityScore.hrv``), in ms."""

    hrv_ms: float
    avg_7d_ms: float | None
    baseline_ms: float | None
    range_low_ms: float | None
    range_high_ms: float | None


@dataclass
class DayResult:
    date: date
    sleep: health_sleep_schema.HealthSleepBase | None = None
    hrv: HrvNight | None = None
    skip: Skip | None = None


def _parse_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _wall_clock(moment: datetime | None, tz: ZoneInfo) -> datetime | None:
    # Upstream's Garmin sync stores "local" times as the local wall clock
    # labelled UTC; do the same so both sources read alike.
    if moment is None:
        return None
    return moment.astimezone(tz).replace(tzinfo=UTC)


def _series(session: dict[str, Any], key: str) -> list[float]:
    points = (session.get("timeseries") or {}).get(key) or []
    return [float(p[1]) for p in points if isinstance(p, list | tuple) and len(p) == 2 and p[1] is not None]


def _int_in(value: float | None, low: int, high: int) -> int | None:
    if value is None:
        return None
    rounded = round(value)
    return rounded if low <= rounded <= high else None


def _stages(session: dict[str, Any], start: datetime | None) -> list[health_sleep_schema.HealthSleepStage] | None:
    if start is None:
        return None
    stages = []
    clock = start
    for item in session.get("stages") or []:
        duration = item.get("duration")
        if not isinstance(duration, int | float) or duration < 0:
            continue
        end = clock + timedelta(seconds=duration)
        stage_type = _STAGES.get(item.get("stage"))
        if stage_type is not None:
            stages.append(
                health_sleep_schema.HealthSleepStage(
                    stage_type=stage_type,
                    start_time_gmt=clock,
                    end_time_gmt=end,
                    duration_seconds=int(duration),
                )
            )
        clock = end
    return stages or None


def _quality(day: dict[str, Any], key: str) -> dict[str, Any]:
    block = (day.get("sleepQualityScore") or {}).get(key)
    return block if isinstance(block, dict) else {}


def _number(value: Any) -> float | None:
    # Eight Sleep marks an open-ended bound with +/-9999.
    if isinstance(value, bool) or not isinstance(value, int | float) or abs(value) >= 9999:
        return None
    return float(value)


def _hrv(day: dict[str, Any]) -> HrvNight | None:
    """The night's HRV as the app shows it (71.5 here is the app's "72")."""
    block = _quality(day, "hrv")
    current = _number(block.get("current"))
    if current is None or current <= 0:
        return None
    return HrvNight(
        hrv_ms=current,
        avg_7d_ms=_number(block.get("inclusive7DayAverage")),
        baseline_ms=_number(block.get("average")),
        range_low_ms=_number(block.get("lowerRange")),
        range_high_ms=_number(block.get("upperRange")),
    )


def _seconds(value: Any) -> int | None:
    return int(value) if isinstance(value, int | float) and value >= 0 else None


def map_day(day: dict[str, Any], default_tz: str) -> DayResult:
    """Map one ``trends`` day record. Never raises on odd data; it skips."""
    day_date = date.fromisoformat(day["day"])
    main_id = day.get("mainSessionId")
    session = next((s for s in day.get("sessions") or [] if s.get("id") == main_id), None)
    if session is None:
        return DayResult(day_date, skip=Skip.NO_MAIN_SESSION)
    # Only ``processing`` means "not final yet". ``incomplete`` is no such signal:
    # 51 nights from 2024 carry it permanently alongside a full score and stages.
    if day.get("processing") or session.get("processing"):
        return DayResult(day_date, skip=Skip.PROCESSING)

    tz = ZoneInfo(session.get("timezone") or default_tz)
    session_start = _parse_utc(session.get("ts"))
    if session_start is not None and DAYTIME_START_HOUR <= session_start.astimezone(tz).hour < DAYTIME_END_HOUR:
        return DayResult(day_date, skip=Skip.DAYTIME)

    total_sleep = _seconds(day.get("sleepDuration"))
    if not total_sleep:
        return DayResult(day_date, skip=Skip.NO_SLEEP)

    sleep_start = _parse_utc(day.get("sleepStart"))
    sleep_end = _parse_utc(day.get("sleepEnd"))
    if sleep_start is not None and sleep_end is not None and sleep_start >= sleep_end:
        sleep_start = sleep_end = None

    heart_rate = _series(session, "heartRate")
    respiration = _series(session, "respiratoryRate")
    score = day.get("score")

    sleep = health_sleep_schema.HealthSleepBase(
        date=day_date,
        sleep_start_time_gmt=sleep_start,
        sleep_end_time_gmt=sleep_end,
        sleep_start_time_local=_wall_clock(sleep_start, tz),
        sleep_end_time_local=_wall_clock(sleep_end, tz),
        total_sleep_seconds=total_sleep,
        deep_sleep_seconds=_seconds(day.get("deepDuration")),
        light_sleep_seconds=_seconds(day.get("lightDuration")),
        rem_sleep_seconds=_seconds(day.get("remDuration")),
        # Awake time between falling asleep and the final wake-up, which is
        # what Garmin's awakeSleepSeconds means too.
        awake_sleep_seconds=_seconds(day.get("wasoDuration")),
        awake_count=_seconds(day.get("wakeupCount")),
        avg_heart_rate=_int_in(statistics.fmean(heart_rate), 20, 220) if heart_rate else None,
        min_heart_rate=_int_in(min(heart_rate), 20, 220) if heart_rate else None,
        max_heart_rate=_int_in(max(heart_rate), 20, 220) if heart_rate else None,
        avg_respiration=_int_in(statistics.fmean(respiration), 0, 100) if respiration else None,
        lowest_respiration=_int_in(min(respiration), 0, 100) if respiration else None,
        highest_respiration=_int_in(max(respiration), 0, 100) if respiration else None,
        sleep_stages=_stages(session, _parse_utc(session.get("ts"))),
        # Eight Sleep's own sleeping heart rate (the app's figure), which feeds
        # upstream's resting-HR page and dashboard tile. Not a clinical resting HR.
        resting_heart_rate=_int_in(_number(_quality(day, "heartRate").get("current")), 20, 220),
        source=health_sleep_schema.Source.EIGHT_SLEEP,
    )
    # Endurain's own per-component labels (duration, awakenings, stage
    # percentages) from the numbers above. The headline score is Eight Sleep's,
    # so it matches the app, and the quality label follows it, as Garmin rows'
    # does Garmin's overall score; Endurain's recomputed quality said POOR
    # beside an Eight Sleep 88.
    health_sleep_scoring._calculate_and_set_sleep_scores(sleep)
    sleep.sleep_score_overall = _int_in(score, 0, 100) if isinstance(score, int | float) else None
    sleep.sleep_score_quality = _band(sleep.sleep_score_overall)
    return DayResult(day_date, sleep=sleep, hrv=_hrv(day))


def _band(score: int | None) -> health_sleep_schema.SleepScore | None:
    # Upstream's bands (sleep_scoring.py).
    if score is None:
        return None
    if score >= 90:
        return health_sleep_schema.SleepScore.EXCELLENT
    if score >= 70:
        return health_sleep_schema.SleepScore.GOOD
    if score >= 50:
        return health_sleep_schema.SleepScore.FAIR
    return health_sleep_schema.SleepScore.POOR
