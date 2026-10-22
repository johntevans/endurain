"""ORM models for ``homelab.training_load_settings`` and ``homelab.activity_loads``.

Both tables are created by ``homelab/alembic/versions/hl0004_training_load.py``,
which also adds the foreign keys to ``users.id`` and ``activities.id``
(ON DELETE CASCADE), not declared here for the reason given in
``homelab.database``.
"""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from homelab.database import HomelabBase


class TrainingLoadSettings(HomelabBase):
    """One athlete's thresholds, as set in Intervals.icu.

    A single row per user, applied to every activity: Intervals does not
    rescore old activities when a threshold changes either. Changing a row
    (``python -m homelab.training_load.cli settings``) recomputes the loads.

    Attributes:
        user_id: Upstream ``users.id``.
        resting_hr: Resting heart rate, bpm.
        threshold_hr: Lactate threshold heart rate, bpm.
        max_hr: Maximum heart rate, bpm.
        threshold_pace: Threshold pace, seconds per kilometre.
        updated_at: When the settings last changed; loads computed before
            this are stale.
    """

    __tablename__ = "training_load_settings"
    __table_args__ = (
        CheckConstraint(
            "resting_hr > 0 AND threshold_hr > resting_hr AND max_hr >= threshold_hr AND threshold_pace > 0",
            name="training_load_settings_range_check",
        ),
    )

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    resting_hr: Mapped[int] = mapped_column(Integer, nullable=False)
    threshold_hr: Mapped[int] = mapped_column(Integer, nullable=False)
    max_hr: Mapped[int] = mapped_column(Integer, nullable=False)
    threshold_pace: Mapped[float] = mapped_column(Float, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class ActivityLoad(HomelabBase):
    """One activity's computed training load: a cache, rebuilt at will.

    Everything here is derived from upstream's tables and the owner's
    ``TrainingLoadSettings``; dropping the rows loses nothing.

    Attributes:
        activity_id: Upstream ``activities.id``.
        load: The Load Intervals would show (pace, else HR; 0 for strength).
        source: ``pace``, ``hr`` or ``none``.
        pace_load: Unrounded pace load, when the activity is a run.
        hr_load: Unrounded HR load, when it has heart rate.
        activity_type: The activity's type when computed; a change of type
            makes the row stale.
        computed_at: When it was computed.
    """

    __tablename__ = "activity_loads"
    __table_args__ = (CheckConstraint("source IN ('pace', 'hr', 'none')", name="activity_loads_source_check"),)

    activity_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    load: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(String(8), nullable=False)
    pace_load: Mapped[float | None] = mapped_column(Float, nullable=True)
    hr_load: Mapped[float | None] = mapped_column(Float, nullable=True)
    activity_type: Mapped[int] = mapped_column(Integer, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
