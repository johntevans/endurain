"""ORM model for ``homelab.lap_intensity_overrides``."""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from homelab.database import HomelabBase


class LapIntensityOverride(HomelabBase):
    """The owner's correction of one lap's intensity.

    Upstream's ``activity_laps.intensity`` is never written: the recorded value
    stays as imported, and a row here takes precedence over it. Laps with no
    recorded value and no row read as the default (see ``schema``).

    The table is created by ``homelab/alembic/versions/hl0003_lap_intensity_overrides.py``,
    which also adds the foreign key to ``activity_laps.id`` (ON DELETE CASCADE),
    not declared here for the reason given in ``homelab.database``.

    Attributes:
        lap_id: Upstream ``activity_laps.id``.
        intensity: One of ``LapIntensityKey``.
        updated_at: When the override was last set.
    """

    __tablename__ = "lap_intensity_overrides"
    __table_args__ = (
        CheckConstraint(
            "intensity IN ('active', 'interval', 'warmup', 'cooldown', 'recovery', 'rest', 'other')",
            name="lap_intensity_overrides_intensity_check",
        ),
    )

    lap_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    intensity: Mapped[str] = mapped_column(String(16), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
