"""The OAuth ``state`` for linking: which user, tamper-proof, short-lived.

It is a Fernet token (``FERNET_KEY``) over ``withings-link:<user_id>``, so it
needs no server-side storage, cannot be forged, and carries its own issue time
for the expiry check.
"""

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
