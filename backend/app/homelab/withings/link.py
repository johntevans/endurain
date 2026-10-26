"""The OAuth ``state`` for linking: which user, tamper-proof, short-lived.

It is a Fernet token (``FERNET_KEY``) over ``withings-link:<user_id>``, so it
needs no server-side storage, cannot be forged, and carries its own issue time
for the expiry check.
"""

from urllib.parse import parse_qs, urlparse

from cryptography.fernet import InvalidToken

import core.cryptography as core_cryptography

PREFIX = "withings-link:"
# Time to click the link and approve; the code itself then has 30 s.
STATE_TTL_SECONDS = 600


def make_state(user_id: int) -> str:
    return core_cryptography.create_fernet_cipher().encrypt(f"{PREFIX}{user_id}".encode()).decode()


def read_state(state: str) -> int | None:
    """The user a state was issued for, or None if it is forged, garbled or expired."""
    try:
        plain = core_cryptography.create_fernet_cipher().decrypt(state.encode(), ttl=STATE_TTL_SECONDS).decode()
    except (InvalidToken, ValueError):
        return None
    if not plain.startswith(PREFIX):
        return None
    try:
        return int(plain[len(PREFIX) :])
    except ValueError:
        return None


# Endurain's own callback route; any other registered callback needs the paste step.
OWN_CALLBACK_PATH = "/public/homelab/withings/callback"


def is_own_callback(redirect_uri: str) -> bool:
    """True when Withings will send the browser to Endurain's own callback."""
    return urlparse(redirect_uri).path.endswith(OWN_CALLBACK_PATH)


def code_from_pasted(pasted: str, state: str) -> tuple[str | None, str | None]:
    """
    The authorization code from what the owner pasted back, for a callback that
    is not Endurain's (the app registered in January points at
    ``http://localhost:8765/callback``, where nothing listens, so the code is
    read from the browser's address bar).

    Accepts the whole address (``...?code=...&state=...``) or the bare code.

    Returns:
        ``(code, None)``, or ``(None, reason)`` when it is unusable.
    """
    text = pasted.strip()
    if not text:
        return None, "nothing was pasted"
    if "=" not in text:
        return (text, None) if " " not in text else (None, "that does not look like an address or a code")
    query = parse_qs(urlparse(text).query if "?" in text else text)
    if "error" in query:
        return None, f"Withings reported: {query['error'][0]}"
    if query.get("state", [state])[0] != state:
        return None, "that address belongs to a different (older) link; use the newest one"
    codes = query.get("code")
    if not codes or not codes[0]:
        return None, "the address has no code in it"
    return codes[0], None
