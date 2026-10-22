"""Minimal client for Eight Sleep's private mobile-app API.

Only two calls: a password-grant token, and the per-day ``trends`` endpoint,
which returns one record per wake-up date with the day's main session marked
(``mainSessionId``) and every session's stages and timeseries.
"""

import os
import time
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import httpx

AUTH_URL = "https://auth-api.8slp.net/v1/tokens"
CLIENT_API_URL = "https://client-api.8slp.net/v1"

# The Android app's OAuth client. Public: shipped in the app and in pyEight
# (lukas-clarke/pyEight, pyeight/constants.py). Overridable in case it rotates.
DEFAULT_CLIENT_ID = "0894c7f33bb94800a03f1f4df13a4f38"
DEFAULT_CLIENT_SECRET = "f0954a3ed5763ba3d06834c73731a32f15f168f47d4f164751275def86db0c76"  # noqa: S105 - the app's public OAuth client, not a credential

# Longest window fetched in one trends call. 30 days is what has been verified.
MAX_DAYS_PER_REQUEST = 30
TOKEN_REFRESH_MARGIN_SECONDS = 120
TIMEOUT_SECONDS = 60
HEADERS = {
    "content-type": "application/json",
    "accept": "application/json",
    "user-agent": "okhttp/4.9.3",
}


class EightSleepError(Exception):
    """Any failure talking to Eight Sleep. Never carries credentials."""


@dataclass
class _Token:
    access_token: str
    user_id: str
    expires_at: float


# One login per token lifetime (~20 h), shared by every job run in the process.
_token: _Token | None = None


def credentials() -> tuple[str, str] | None:
    """The configured Eight Sleep login, or None when the integration is off."""
    email = os.environ.get("EIGHT_SLEEP_EMAIL", "").strip()
    password = os.environ.get("EIGHT_SLEEP_PASSWORD", "")
    if not email or not password:
        return None
    return email, password


def owns_sleep() -> bool:
    """True when Eight Sleep is configured; upstream's Garmin sleep fetch then stands aside."""
    return credentials() is not None


def _login(client: httpx.Client) -> _Token:
    creds = credentials()
    if creds is None:
        raise EightSleepError("EIGHT_SLEEP_EMAIL / EIGHT_SLEEP_PASSWORD are not set")
    body = {
        "client_id": os.environ.get("EIGHT_SLEEP_CLIENT_ID", DEFAULT_CLIENT_ID),
        "client_secret": os.environ.get("EIGHT_SLEEP_CLIENT_SECRET", DEFAULT_CLIENT_SECRET),
        "grant_type": "password",
        "username": creds[0],
        "password": creds[1],
    }
    response = client.post(AUTH_URL, json=body, headers=HEADERS)
    if response.status_code != 200:
        # The body is not logged: it could echo the request.
        raise EightSleepError(f"login failed with HTTP {response.status_code}")
    payload = response.json()
    return _Token(
        access_token=payload["access_token"],
        user_id=payload["userId"],
        expires_at=time.time() + float(payload["expires_in"]),
    )


def _get_token(client: httpx.Client, force: bool = False) -> _Token:
    global _token
    if force or _token is None or _token.expires_at - TOKEN_REFRESH_MARGIN_SECONDS < time.time():
        _token = _login(client)
    return _token


def _get(client: httpx.Client, path: str, params: dict[str, str]) -> dict[str, Any]:
    token = _get_token(client)
    for attempt in (1, 2):
        response = client.get(
            f"{CLIENT_API_URL}/users/{token.user_id}{path}",
            params=params,
            headers={**HEADERS, "authorization": f"Bearer {token.access_token}"},
        )
        if response.status_code == 401 and attempt == 1:
            token = _get_token(client, force=True)
            continue
        if response.status_code != 200:
            raise EightSleepError(f"GET {path} failed with HTTP {response.status_code}")
        return response.json()
    raise EightSleepError(f"GET {path} still unauthorised after a fresh login")


def fetch_days(start: date, end: date, tz: str) -> list[dict[str, Any]]:
    """
    Every Eight Sleep day record from ``start`` to ``end`` inclusive.

    Raises EightSleepError on any failed call, so a caller never mistakes a
    failed fetch for "no data" (which would read as deletions).
    """
    days: list[dict[str, Any]] = []
    with httpx.Client(timeout=TIMEOUT_SECONDS) as client:
        chunk_start = start
        while chunk_start <= end:
            chunk_end = min(chunk_start + timedelta(days=MAX_DAYS_PER_REQUEST - 1), end)
            payload = _get(
                client,
                "/trends",
                {
                    "tz": tz,
                    "from": chunk_start.isoformat(),
                    "to": chunk_end.isoformat(),
                    "include-main": "false",
                    "include-all-sessions": "true",
                    "model-version": "v2",
                },
            )
            if not isinstance(payload.get("days"), list):
                raise EightSleepError("trends response has no 'days' list")
            days.extend(payload["days"])
            chunk_start = chunk_end + timedelta(days=1)
    return days
