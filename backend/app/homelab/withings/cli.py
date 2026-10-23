"""Link Withings and check the link.

In the backend container, from ``/app/backend``::

    python -m homelab.withings.cli link [--user-id N]   # prints the approval URL (valid 10 min)
    python -m homelab.withings.cli status [--user-id N] # linked? token expiry? (never prints a token)
    python -m homelab.withings.cli refresh [--user-id N] # force a refresh now, to prove it works

``--user-id`` defaults to the only user when there is exactly one.
"""

import argparse
import pathlib
import sys
from datetime import UTC, datetime
from importlib import import_module

from sqlalchemy import select

import users.users.models as users_models
from core.database import SessionLocal
from homelab.withings import client as withings_client
from homelab.withings import link as withings_link
from homelab.withings import tokens as withings_tokens
from homelab.withings.models import WithingsToken


def _import_all_models() -> None:
    # Outside the app nothing imports every model, and the mappers need them all
    # (as in homelab.training_load.cli).
    app_dir = pathlib.Path(__file__).resolve().parents[2]
    for path in sorted(app_dir.glob("**/models.py")):
        import_module(".".join(path.relative_to(app_dir).with_suffix("").parts))


def _user_id(db, given: int | None) -> int:
    if given is not None:
        return given
    ids = db.execute(select(users_models.Users.id)).scalars().all()
    if len(ids) != 1:
        sys.exit(f"{len(ids)} users; pass --user-id")
    return ids[0]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m homelab.withings.cli")
    parser.add_argument("command", choices=["link", "status", "refresh"])
    parser.add_argument("--user-id", type=int)
    args = parser.parse_args(argv)
    _import_all_models()
    cfg = withings_client.config()
    with SessionLocal() as db:
        user_id = _user_id(db, args.user_id)
        if args.command == "link":
            if cfg is None:
                print("Withings is not configured: set WITHINGS_CLIENT_ID, _SECRET and _REDIRECT_URI.")  # noqa: T201 - CLI output
                return 1
            print("Open this within 10 minutes, approve, and the callback finishes the link:")  # noqa: T201 - CLI output
            print(withings_client.authorize_url(cfg, withings_link.make_state(user_id)))  # noqa: T201 - CLI output
            return 0
        row = db.get(WithingsToken, user_id)
        if row is None:
            print(f"user {user_id}: not linked")  # noqa: T201 - CLI output
            return 1
        if args.command == "refresh":
            row.expires_at = datetime(1970, 1, 1, tzinfo=UTC)
            db.commit()
            withings_tokens.access_token(user_id, db)
            db.expire_all()
            row = db.get(WithingsToken, user_id)
        expires = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=UTC)
        left = (expires - datetime.now(UTC)).total_seconds() / 60
        print(  # noqa: T201 - CLI output
            f"user {user_id}: linked to Withings user {row.withings_userid}, scope {row.scope}, "
            f"access token expires {expires:%Y-%m-%d %H:%M} UTC ({left:.0f} min), updated {row.updated_at:%Y-%m-%d %H:%M}"
        )
        return 0


if __name__ == "__main__":
    sys.exit(main())
