"""Withings OAuth 2.0: the authorize link and the token endpoint.

Reference: https://developer.withings.com/llms.md. An authorization code is
valid for 30 seconds, so the callback exchanges it at once; an access token
lasts 3 hours; a refresh token 12 months, and each refresh replaces it.
"""

import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx

AUTHORIZE_URL = "https://account.withings.com/oauth2_user/authorize2"
TOKEN_URL = "https://wbsapi.withings.net/v2/oauth2"  # noqa: S105 - a URL, not a secret
SCOPE = "user.metrics"
TIMEOUT_SECONDS = 30


class WithingsError(Exception):
    """Any failure talking to Withings. Never carries a token or the secret."""


@dataclass(frozen=True)
class WithingsConfig:
    client_id: str
    client_secret: str
    redirect_uri: str


@dataclass(frozen=True)
class TokenSet:
    withings_userid: str
    access_token: str
    refresh_token: str
    expires_at: datetime
    scope: str


def config() -> WithingsConfig | None:
    """The configured Withings app, or None when the integration is off."""
    client_id = os.environ.get("WITHINGS_CLIENT_ID", "").strip()
    client_secret = os.environ.get("WITHINGS_CLIENT_SECRET", "").strip()
    redirect_uri = os.environ.get("WITHINGS_REDIRECT_URI", "").strip()
    if not (client_id and client_secret and redirect_uri):
        return None
    return WithingsConfig(client_id, client_secret, redirect_uri)


def authorize_url(cfg: WithingsConfig, state: str) -> str:
    """The page where the owner approves access."""
    query = {
        "response_type": "code",
        "client_id": cfg.client_id,
        "scope": SCOPE,
        "redirect_uri": cfg.redirect_uri,
        "state": state,
    }
    return f"{AUTHORIZE_URL}?{urlencode(query)}"


def _request_token(cfg: WithingsConfig, grant: dict[str, str]) -> TokenSet:
    body = {"action": "requesttoken", "client_id": cfg.client_id, "client_secret": cfg.client_secret, **grant}
    try:
        response = httpx.post(TOKEN_URL, data=body, timeout=TIMEOUT_SECONDS)
    except httpx.HTTPError as err:
        raise WithingsError(f"token request failed: {type(err).__name__}") from err
    if response.status_code != 200:
        raise WithingsError(f"token request failed with HTTP {response.status_code}")
    payload: dict[str, Any] = response.json()
    # Withings answers HTTP 200 with its own status; 0 is success.
    if payload.get("status") != 0:
        raise WithingsError(f"token request refused: status {payload.get('status')} {payload.get('error', '')}".strip())
    token = payload["body"]
    return TokenSet(
        withings_userid=str(token["userid"]),
        access_token=token["access_token"],
        refresh_token=token["refresh_token"],
        expires_at=datetime.now(UTC) + timedelta(seconds=int(token["expires_in"])),
        scope=str(token.get("scope", "")),
    )


def exchange_code(cfg: WithingsConfig, code: str) -> TokenSet:
    """Swap an authorization code (valid 30 s) for tokens."""
    return _request_token(cfg, {"grant_type": "authorization_code", "code": code, "redirect_uri": cfg.redirect_uri})


def refresh(cfg: WithingsConfig, refresh_token: str) -> TokenSet:
    """New tokens from a refresh token. The returned refresh token REPLACES the old one."""
    return _request_token(cfg, {"grant_type": "refresh_token", "refresh_token": refresh_token})
