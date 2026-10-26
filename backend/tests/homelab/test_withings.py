"""Homelab fork: Withings linking (OAuth client, state, encrypted tokens, callback)."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import text
from sqlalchemy.orm import Session

import core.cryptography as core_cryptography
from homelab.database import HomelabBase
from homelab.withings import client as withings_client
from homelab.withings import link as withings_link
from homelab.withings import public_router
from homelab.withings import tokens as withings_tokens
from homelab.withings.models import WithingsToken
from tests._helpers.db import create_sqlite_session

USER = 1
CFG = withings_client.WithingsConfig("cid", "csecret", "https://tempo.example/api/v1/public/homelab/withings/callback")


@pytest.fixture(autouse=True)
def fernet_key(monkeypatch):
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())


@pytest.fixture
def db() -> Iterator[Session]:
    session = create_sqlite_session()
    session.execute(text("ATTACH DATABASE ':memory:' AS homelab"))
    HomelabBase.metadata.create_all(session.connection())
    session.commit()
    try:
        yield session
    finally:
        session.close()
        session.bind.dispose()


def _tokens(access="acc-1", refresh="ref-1", minutes=180) -> withings_client.TokenSet:
    return withings_client.TokenSet(
        "w42", access, refresh, datetime.now(UTC) + timedelta(minutes=minutes), "user.metrics"
    )


def _response(payload, status=200):
    response = MagicMock(status_code=status)
    response.json.return_value = payload
    return response


class TestClient:
    def test_config_needs_all_three_settings(self, monkeypatch):
        monkeypatch.setenv("WITHINGS_CLIENT_ID", "cid")
        monkeypatch.setenv("WITHINGS_CLIENT_SECRET", "csecret")
        monkeypatch.delenv("WITHINGS_REDIRECT_URI", raising=False)
        assert withings_client.config() is None
        monkeypatch.setenv("WITHINGS_REDIRECT_URI", CFG.redirect_uri)
        assert withings_client.config() == CFG

    def test_authorize_url_asks_only_for_metrics(self):
        query = parse_qs(urlparse(withings_client.authorize_url(CFG, "st")).query)
        assert query == {
            "response_type": ["code"],
            "client_id": ["cid"],
            "scope": ["user.metrics"],
            "redirect_uri": [CFG.redirect_uri],
            "state": ["st"],
        }

    def test_exchange_posts_the_code_and_parses_the_tokens(self):
        body = {"userid": 42, "access_token": "a", "refresh_token": "r", "expires_in": 10800, "scope": "user.metrics"}
        with patch.object(withings_client.httpx, "post", return_value=_response({"status": 0, "body": body})) as post:
            tokens = withings_client.exchange_code(CFG, "the-code")

        sent = post.call_args.kwargs["data"]
        assert sent["grant_type"] == "authorization_code"
        assert sent["code"] == "the-code"
        assert sent["redirect_uri"] == CFG.redirect_uri
        assert (tokens.withings_userid, tokens.access_token, tokens.refresh_token) == ("42", "a", "r")
        assert timedelta(minutes=179) < tokens.expires_at - datetime.now(UTC) <= timedelta(minutes=180)

    @pytest.mark.parametrize(
        "response",
        [_response({"status": 503, "error": "Invalid code"}), _response({}, status=500)],
    )
    def test_a_refusal_raises_without_leaking_the_secret(self, response):
        with (
            patch.object(withings_client.httpx, "post", return_value=response),
            pytest.raises(withings_client.WithingsError) as raised,
        ):
            withings_client.refresh(CFG, "old-refresh")
        assert "csecret" not in str(raised.value)
        assert "old-refresh" not in str(raised.value)


class TestState:
    def test_round_trip(self):
        assert withings_link.read_state(withings_link.make_state(7)) == 7

    def test_forged_or_garbled_state_is_rejected(self):
        other = Fernet(Fernet.generate_key()).encrypt(b"withings-link:7").decode()
        assert withings_link.read_state(other) is None
        assert withings_link.read_state("not-a-token") is None

    def test_state_for_something_else_is_rejected(self):
        state = core_cryptography.create_fernet_cipher().encrypt(b"something-else:7").decode()
        assert withings_link.read_state(state) is None

    def test_expired_state_is_rejected(self):
        cipher = core_cryptography.create_fernet_cipher()
        old = cipher.encrypt_at_time(b"withings-link:7", int(datetime.now(UTC).timestamp()) - 3600).decode()
        assert withings_link.read_state(old) is None


class TestTokens:
    def test_tokens_are_stored_encrypted(self, db):
        withings_tokens.save(USER, _tokens(), db)

        row = db.get(WithingsToken, USER)
        assert row.access_token != "acc-1"
        assert row.refresh_token != "ref-1"
        assert core_cryptography.decrypt_token_fernet(row.refresh_token) == "ref-1"

    def test_a_fresh_token_is_used_without_refreshing(self, db):
        withings_tokens.save(USER, _tokens(), db)
        with patch.object(withings_client, "refresh") as refresh:
            assert withings_tokens.access_token(USER, db) == "acc-1"
        refresh.assert_not_called()

    def test_a_token_near_expiry_is_refreshed_and_the_refresh_token_replaced(self, db, monkeypatch):
        monkeypatch.setattr(withings_client, "config", lambda: CFG)
        withings_tokens.save(USER, _tokens(minutes=5), db)
        with patch.object(withings_client, "refresh", return_value=_tokens("acc-2", "ref-2")) as refresh:
            assert withings_tokens.access_token(USER, db) == "acc-2"

        assert refresh.call_args.args == (CFG, "ref-1")
        db.expire_all()
        assert core_cryptography.decrypt_token_fernet(db.get(WithingsToken, USER).refresh_token) == "ref-2"

    def test_a_failed_refresh_keeps_the_old_link(self, db, monkeypatch):
        monkeypatch.setattr(withings_client, "config", lambda: CFG)
        withings_tokens.save(USER, _tokens(minutes=5), db)
        with (
            patch.object(withings_client, "refresh", side_effect=withings_client.WithingsError("status 401")),
            pytest.raises(withings_client.WithingsError),
        ):
            withings_tokens.access_token(USER, db)

        db.expire_all()
        assert core_cryptography.decrypt_token_fernet(db.get(WithingsToken, USER).refresh_token) == "ref-1"

    def test_not_linked_is_none(self, db):
        assert withings_tokens.access_token(USER, db) is None


class TestCallback:
    def _client(self, db):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient as HttpClient

        import core.database as core_db

        app = FastAPI()
        app.include_router(public_router.router, prefix="/withings")
        app.dependency_overrides[core_db.get_db] = lambda: db
        return HttpClient(app)

    def test_a_bare_get_or_head_answers_200_for_the_dashboard_check(self, db):
        client = self._client(db)
        assert client.get("/withings/callback").status_code == 200
        assert client.head("/withings/callback").status_code == 200

    def test_a_valid_state_links_the_user(self, db, monkeypatch):
        monkeypatch.setattr(withings_client, "config", lambda: CFG)
        with patch.object(withings_client, "exchange_code", return_value=_tokens()) as exchange:
            response = self._client(db).get(
                "/withings/callback", params={"code": "c0de", "state": withings_link.make_state(USER)}
            )

        assert response.status_code == 200
        assert "Withings linked" in response.text
        assert exchange.call_args.args == (CFG, "c0de")
        assert db.get(WithingsToken, USER) is not None
        assert "acc-1" not in response.text

    @pytest.mark.parametrize(
        ("params", "status"),
        [
            ({"code": "c", "state": "forged"}, 400),
            ({"error": "access_denied", "state": "x"}, 400),
        ],
    )
    def test_bad_requests_link_nothing(self, db, params, status):
        with patch.object(withings_client, "exchange_code") as exchange:
            response = self._client(db).get("/withings/callback", params=params)

        assert response.status_code == status
        exchange.assert_not_called()
        assert db.get(WithingsToken, USER) is None

    def test_unconfigured_is_503(self, db, monkeypatch):
        monkeypatch.setattr(withings_client, "config", lambda: None)
        response = self._client(db).get(
            "/withings/callback", params={"code": "c", "state": withings_link.make_state(USER)}
        )
        assert response.status_code == 503

    def test_a_refused_code_is_502_and_links_nothing(self, db, monkeypatch):
        monkeypatch.setattr(withings_client, "config", lambda: CFG)
        with patch.object(withings_client, "exchange_code", side_effect=withings_client.WithingsError("status 503")):
            response = self._client(db).get(
                "/withings/callback", params={"code": "c", "state": withings_link.make_state(USER)}
            )

        assert response.status_code == 502
        assert db.get(WithingsToken, USER) is None


class TestPasteLink:
    def test_only_endurains_own_callback_skips_the_paste_step(self):
        assert withings_link.is_own_callback(CFG.redirect_uri)
        assert not withings_link.is_own_callback("http://localhost:8765/callback")

    def test_the_whole_address_or_the_bare_code_is_accepted(self):
        state = withings_link.make_state(USER)
        url = f"http://localhost:8765/callback?code=abc123&state={state}"
        assert withings_link.code_from_pasted(url, state) == ("abc123", None)
        assert withings_link.code_from_pasted("  abc123 \n", state) == ("abc123", None)

    @pytest.mark.parametrize(
        ("pasted", "reason"),
        [
            ("", "nothing was pasted"),
            ("http://localhost:8765/callback?error=access_denied&state={state}", "access_denied"),
            ("http://localhost:8765/callback?code=abc&state=older", "different"),
            ("http://localhost:8765/callback?state={state}", "no code"),
            ("not a code", "does not look"),
        ],
    )
    def test_unusable_pastes_are_refused(self, pasted, reason):
        state = withings_link.make_state(USER)
        code, problem = withings_link.code_from_pasted(pasted.format(state=state), state)
        assert code is None
        assert reason in problem

    def test_link_exchanges_the_pasted_code_and_stores_the_tokens(self, db, monkeypatch, capsys):
        from homelab.withings import cli

        local = withings_client.WithingsConfig("cid", "csecret", "http://localhost:8765/callback")
        monkeypatch.setattr(withings_client, "config", lambda: local)
        monkeypatch.setattr(cli, "SessionLocal", lambda: db)
        monkeypatch.setattr(cli, "_import_all_models", lambda: None)
        monkeypatch.setattr(cli, "_user_id", lambda _db, _given: USER)

        def paste_back(_prompt):
            printed = capsys.readouterr().out
            state = parse_qs(urlparse(printed.split("   ", 1)[1].split()[0]).query)["state"][0]
            return f"http://localhost:8765/callback?code=c0de&state={state}"

        monkeypatch.setattr("builtins.input", paste_back)
        with patch.object(withings_client, "exchange_code", return_value=_tokens()) as exchange:
            assert cli.main(["link"]) == 0

        assert exchange.call_args.args == (local, "c0de")
        assert db.get(WithingsToken, USER) is not None
        assert "acc-1" not in capsys.readouterr().out

    def test_a_refused_code_links_nothing(self, db, monkeypatch, capsys):
        from homelab.withings import cli

        local = withings_client.WithingsConfig("cid", "csecret", "http://localhost:8765/callback")
        monkeypatch.setattr(withings_client, "config", lambda: local)
        monkeypatch.setattr(cli, "SessionLocal", lambda: db)
        monkeypatch.setattr(cli, "_import_all_models", lambda: None)
        monkeypatch.setattr(cli, "_user_id", lambda _db, _given: USER)
        monkeypatch.setattr("builtins.input", lambda _prompt: "c0de")
        with patch.object(withings_client, "exchange_code", side_effect=withings_client.WithingsError("status 503")):
            assert cli.main(["link"]) == 1

        assert db.get(WithingsToken, USER) is None
