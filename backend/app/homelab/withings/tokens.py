"""Storing and refreshing the Withings tokens (encrypted at rest)."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

import core.cryptography as core_cryptography
from homelab.withings import client as withings_client
from homelab.withings.models import WithingsToken

# Refresh this long before expiry, so a sync never starts with a token about to lapse.
REFRESH_MARGIN = timedelta(minutes=10)


def save(user_id: int, tokens: withings_client.TokenSet, db: Session) -> None:
    """Store (or replace) a user's link."""
    row = db.get(WithingsToken, user_id)
    if row is None:
        row = WithingsToken(user_id=user_id)
        db.add(row)
    row.withings_userid = tokens.withings_userid
    row.access_token = core_cryptography.encrypt_token_fernet(tokens.access_token)
    row.refresh_token = core_cryptography.encrypt_token_fernet(tokens.refresh_token)
    row.expires_at = tokens.expires_at
    row.scope = tokens.scope
    db.commit()


def access_token(user_id: int, db: Session) -> str | None:
    """
    A valid access token for the user, refreshing it first if it is close to expiry.

    The row is locked for the refresh: a refresh token works once, so two
    concurrent refreshes would leave whichever lost holding a dead token.

    Returns:
        The token, or None when the user has not linked Withings.

    Raises:
        WithingsError: Withings is not configured, or refused the refresh
            (then the link must be made again: ``cli link``).
    """
    row = db.execute(
        select(WithingsToken).where(WithingsToken.user_id == user_id).with_for_update()
    ).scalar_one_or_none()
    if row is None:
        db.rollback()
        return None
    expires_at = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=UTC)
    if expires_at - REFRESH_MARGIN > datetime.now(UTC):
        token = core_cryptography.decrypt_token_fernet(row.access_token)
        db.rollback()
        return token
    cfg = withings_client.config()
    if cfg is None:
        db.rollback()
        raise withings_client.WithingsError("WITHINGS_CLIENT_ID / _SECRET / _REDIRECT_URI are not set")
    try:
        fresh = withings_client.refresh(cfg, core_cryptography.decrypt_token_fernet(row.refresh_token))
    except withings_client.WithingsError:
        db.rollback()
        raise
    save(user_id, fresh, db)
    return fresh.access_token
