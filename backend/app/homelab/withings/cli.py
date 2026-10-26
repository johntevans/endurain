"""Link Withings and check the link.

In the backend container, from ``/app/backend``::

    python -m homelab.withings.cli link [--user-id N]   # prints the approval URL (valid 10 min); when the
                                                        # registered callback is not Endurain's, waits for
                                                        # the browser's address to be pasted back (run with -it)
    python -m homelab.withings.cli status [--user-id N] # linked? token expiry? (never prints a token)
    python -m homelab.withings.cli refresh [--user-id N] # force a refresh now, to prove it works
    python -m homelab.withings.cli garmin-push [--dry-run] [--limit N] [--since YYYY-MM-DD]
                                                         # forward the weigh-ins Garmin lacks

``--user-id`` defaults to the only user when there is exactly one.
"""

import argparse
import pathlib
import sys
from datetime import UTC, date, datetime
from importlib import import_module

from sqlalchemy import select

import users.users.models as users_models
from core.database import SessionLocal
from homelab.withings import client as withings_client
from homelab.withings import garmin_push as withings_garmin_push
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


def _link_by_paste(cfg, user_id: int, state: str, url: str, db) -> int:
    """Link through a callback Endurain does not serve: the owner pastes the address back."""
    print(  # noqa: T201 - CLI output
        "1. Open this link and sign in, but do NOT click Allow until step 2 is ready:\n"
        f"   {url}\n"
        f"2. Click Allow. Your browser then fails to open {cfg.redirect_uri}: that is expected.\n"
        "3. Copy the WHOLE address from the browser's address bar and paste it below.\n"
        "   Withings codes expire 30 seconds after Allow, so paste straight away."
    )
    try:
        pasted = input("address> ")
    except EOFError:
        print("No input; nothing was changed.")  # noqa: T201 - CLI output
        return 1
    code, problem = withings_link.code_from_pasted(pasted, state)
    if problem:
        print(f"Not linked: {problem}. Nothing was changed; run link again.")  # noqa: T201 - CLI output
        return 1
    try:
        tokens = withings_client.exchange_code(cfg, code)
    except withings_client.WithingsError as err:
        print(f"Not linked: Withings refused the code ({err}). It may have expired; run link again.")  # noqa: T201 - CLI output
        return 1
    withings_tokens.save(user_id, tokens, db)
    print(f"Linked: Endurain user {user_id} -> Withings user {tokens.withings_userid}, scope {tokens.scope}.")  # noqa: T201 - CLI output
    return 0


def _garmin_push(user_id: int, args, db) -> int:
    """Forward the Withings weigh-ins Garmin lacks (whole history unless --since)."""
    token = withings_tokens.access_token(user_id, db)
    if token is None:
        print(f"user {user_id}: Withings not linked")  # noqa: T201 - CLI output
        return 1
    groups, _ = withings_client.get_measure_groups(token)
    start = args.since or date(2000, 1, 1)
    counts, todo = withings_garmin_push.push(
        user_id, groups, start, date.today(), db, limit=args.limit, dry_run=args.dry_run
    )
    verb = "would upload" if args.dry_run else "uploaded"
    for w in todo:
        print(  # noqa: T201 - CLI output
            f"  {verb} {w.at:%Y-%m-%d %H:%M} UTC  {w.weight:.2f} kg"
            f"  fat {w.percent_fat if w.percent_fat is not None else '-'}%"
        )
    print(", ".join(f"{n} {k}" for k, n in sorted(counts.items())) or "nothing to do")  # noqa: T201 - CLI output
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m homelab.withings.cli")
    parser.add_argument("command", choices=["link", "status", "refresh", "garmin-push"])
    parser.add_argument("--user-id", type=int)
    parser.add_argument("--dry-run", action="store_true", help="garmin-push: list, upload nothing")
    parser.add_argument("--limit", type=int, help="garmin-push: upload at most N (oldest first)")
    parser.add_argument("--since", type=date.fromisoformat, help="garmin-push: only weigh-ins from this date")
    args = parser.parse_args(argv)
    _import_all_models()
    cfg = withings_client.config()
    with SessionLocal() as db:
        user_id = _user_id(db, args.user_id)
        if args.command == "link":
            if cfg is None:
                print("Withings is not configured: set WITHINGS_CLIENT_ID, _SECRET and _REDIRECT_URI.")  # noqa: T201 - CLI output
                return 1
            state = withings_link.make_state(user_id)
            url = withings_client.authorize_url(cfg, state)
            if withings_link.is_own_callback(cfg.redirect_uri):
                print("Open this within 10 minutes, approve, and the callback finishes the link:")  # noqa: T201 - CLI output
                print(url)  # noqa: T201 - CLI output
                return 0
            return _link_by_paste(cfg, user_id, state, url, db)
        if args.command == "garmin-push":
            return _garmin_push(user_id, args, db)
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
