"""ORM models for ``homelab.sleep_hrv`` and ``homelab.sleep_heart_rate``.

Created by ``hl0005_sleep_hrv.py`` and ``hl0006_sleep_heart_rate.py``, which also add the
foreign key to ``users.id`` (ON DELETE CASCADE), not declared here for the
reason given in ``homelab.database``.
"""

from datetime import date

from sqlalchemy import CheckConstraint, Date, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from homelab.database import HomelabBase


class SleepHrv(HomelabBase):
    """One night's heart-rate variability, as Eight Sleep reports it.

    Upstream's ``health_sleep`` has no numeric HRV column (only Garmin's status
    label), so it lives here, one row per user and wake-up date, the same date
    as that night's ``health_sleep`` row. Every value is Eight Sleep's own
    (``sleepQualityScore.hrv``), not recomputed, so it matches the app.

    Attributes:
        user_id: Upstream ``users.id``.
        date: Wake-up date, as in ``health_sleep.date``.
        hrv_ms: The night's HRV (RMSSD, ms): what the app shows.
        avg_7d_ms: Eight Sleep's 7-day average including this night.
        baseline_ms: Eight Sleep's long-run average for this user.
        range_low_ms: Lower edge of the usual range.
        range_high_ms: Upper edge of the usual range.
        source: Where it came from; only ``eight_sleep`` today.
    """

    __tablename__ = "sleep_hrv"
    __table_args__ = (CheckConstraint("hrv_ms > 0", name="sleep_hrv_hrv_ms_check"),)

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    hrv_ms: Mapped[float] = mapped_column(Float, nullable=False)
    avg_7d_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    baseline_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    range_low_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    range_high_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="eight_sleep")


class SleepHeartRate(HomelabBase):
    """One night's sleeping heart rate, as Eight Sleep reports it.

    The same shape as :class:`SleepHrv`, from ``sleepQualityScore.heartRate``.
    The night's value is also written to upstream's
    ``health_sleep.resting_heart_rate``; this table adds what upstream has no
    column for: the 7-day average, baseline and usual range.

    Attributes:
        user_id: Upstream ``users.id``.
        date: Wake-up date, as in ``health_sleep.date``.
        hr_bpm: The night's sleeping heart rate: what the app shows.
        avg_7d_bpm: Eight Sleep's 7-day average including this night.
        baseline_bpm: Eight Sleep's long-run average for this user.
        range_low_bpm: Lower edge of the usual range.
        range_high_bpm: Upper edge of the usual range.
        source: Where it came from; only ``eight_sleep`` today.
    """

    __tablename__ = "sleep_heart_rate"
    __table_args__ = (CheckConstraint("hr_bpm > 0", name="sleep_heart_rate_hr_bpm_check"),)

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    hr_bpm: Mapped[float] = mapped_column(Float, nullable=False)
    avg_7d_bpm: Mapped[float | None] = mapped_column(Float, nullable=True)
    baseline_bpm: Mapped[float | None] = mapped_column(Float, nullable=True)
    range_low_bpm: Mapped[float | None] = mapped_column(Float, nullable=True)
    range_high_bpm: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="eight_sleep")
