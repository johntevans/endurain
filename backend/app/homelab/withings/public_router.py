"""Withings OAuth callback (homelab fork), unauthenticated by necessity.

Mounted at ``/api/v1/public/homelab/withings`` by ``homelab.routes``. Withings
redirects the owner's browser here after approval; the ``state`` (see
``link.py``) is what ties the request to a user, so nothing else is trusted.
Answers a bare GET or HEAD with 200 so a URL check in the Withings developer
dashboard passes. Pages are plain HTML and never echo a token.
"""

from html import escape
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

import core.database as core_database
import core.logger as core_logger
from homelab.withings import client as withings_client
from homelab.withings import link as withings_link
from homelab.withings import tokens as withings_tokens

router = APIRouter()


def _page(title: str, message: str, status_code: int = 200) -> HTMLResponse:
    body = (
        "<!doctype html><meta charset='utf-8'><meta name='viewport' content='width=device-width'>"
        f"<title>{escape(title)}</title>"
        "<body style='font-family:system-ui,sans-serif;max-width:32rem;margin:3rem auto;padding:0 1rem'>"
        f"<h1>{escape(title)}</h1><p>{escape(message)}</p></body>"
    )
    return HTMLResponse(body, status_code=status_code)


@router.api_route("/callback", methods=["GET", "HEAD"], response_class=HTMLResponse)
def withings_callback(
    db: Annotated[Session, Depends(core_database.get_db)],
    code: Annotated[str | None, Query(max_length=512)] = None,
    state: Annotated[str | None, Query(max_length=1024)] = None,
    error: Annotated[str | None, Query(max_length=256)] = None,
) -> HTMLResponse:
    """Finish linking: check the state, exchange the code, store the tokens."""
    if error:
        return _page("Withings not linked", f"Withings reported: {error}. Nothing was changed.", 400)
    if not code and not state:
        return _page("Withings callback", "This is Endurain's Withings callback. It is ready.")
    user_id = withings_link.read_state(state or "")
    if user_id is None:
        return _page(
            "Link expired or invalid",
            "This approval link is older than 10 minutes or was not issued by Endurain. Ask for a new one.",
            400,
        )
    cfg = withings_client.config()
    if cfg is None:
        return _page("Withings is not configured", "Endurain has no Withings client ID, secret or callback URL.", 503)
    if not code:
        return _page("Withings not linked", "Withings sent no authorization code. Nothing was changed.", 400)
    try:
        tokens = withings_client.exchange_code(cfg, code)
    except withings_client.WithingsError as err:
        core_logger.print_to_log(f"Withings link for user {user_id} failed: {err}", "error")
        return _page(
            "Withings not linked",
            f"Withings refused the code ({err}). Codes last 30 seconds; ask for a new link and approve promptly.",
            502,
        )
    withings_tokens.save(user_id, tokens, db)
    core_logger.print_to_log(f"Withings linked for user {user_id} (Withings user {tokens.withings_userid})")
    return _page("Withings linked", "Endurain can now read your Withings weight. You can close this tab.")
