"""ORM model for ``homelab.withings_tokens``.

Created by ``homelab/alembic/versions/hl0007_withings_tokens.py``, which also
adds the foreign key to ``users.id`` (ON DELETE CASCADE), not declared here for
the reason given in ``homelab.database``.
"""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from homelab.database import HomelabBase


class WithingsToken(HomelabBase):
    """One user's Withings link. Both tokens are Fernet-encrypted (``FERNET_KEY``).

    Attributes:
        user_id: Upstream ``users.id``.
        withings_userid: The Withings account's own id.
        access_token: Encrypted access token (lasts 3 h).
        refresh_token: Encrypted refresh token (12 months; replaced on every refresh).
        expires_at: When the access token expires.
        scope: Scopes granted.
        updated_at: Last link or refresh.
    """

    __tablename__ = "withings_tokens"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    withings_userid: Mapped[str] = mapped_column(String(32), nullable=False)
    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    scope: Mapped[str] = mapped_column(String(128), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
