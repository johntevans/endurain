"""Homelab fork: activity tags (crud, visibility, list/count AND filter, routes).

Access control and the tag filter are SQL ``WHERE`` clauses, so they run
against a real in-memory SQLite database with the ``homelab`` schema attached
(SQLite's stand-in for a Postgres schema).
"""

from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

import modules.activities.activity.crud as activities_crud
import modules.activities.activity.models as activities_models
import modules.followers.models as followers_models
from homelab.activity_tags import crud as tags_crud
from homelab.activity_tags import filters as tags_filters
from homelab.activity_tags.models import ActivityTag
from homelab.activity_tags.schema import ActivityTagKey, sort_tags
from homelab.database import HomelabBase
from tests._helpers.db import create_sqlite_session

OWNER = 1
FOLLOWER = 2
STRANGER = 3


@pytest.fixture
def db() -> Iterator[Session]:
    """SQLite session with upstream tables plus the attached ``homelab`` schema."""
    session = create_sqlite_session()
    session.execute(text("ATTACH DATABASE ':memory:' AS homelab"))
    HomelabBase.metadata.create_all(session.connection())
    session.commit()
    try:
        yield session
    finally:
        session.close()
        session.bind.dispose()


def _activity(activity_id: int, **overrides) -> activities_models.Activity:
    fields = {
        "id": activity_id,
        "user_id": OWNER,
        "name": f"Activity {activity_id}",
        "distance": 1000,
        "activity_type": 1,
        "start_time": datetime(2024, 1, activity_id, tzinfo=UTC),
        "end_time": datetime(2024, 1, activity_id, 1, tzinfo=UTC),
        "created_at": datetime(2024, 1, 1, tzinfo=UTC),
        "total_elapsed_time": Decimal("3600"),
        "total_timer_time": Decimal("3600"),
        "visibility": 0,
        "is_hidden": False,
        **dict.fromkeys(
            [
                "hide_start_time",
                "hide_location",
                "hide_map",
                "hide_hr",
                "hide_power",
                "hide_cadence",
                "hide_elevation",
                "hide_speed",
                "hide_pace",
                "hide_laps",
                "hide_workout_sets_steps",
                "hide_gear",
            ],
            False,
        ),
    }
    fields.update(overrides)
    return activities_models.Activity(**fields)


def _tag(db: Session, activity_id: int, *tags: str) -> None:
    for tag in tags:
        db.add(ActivityTag(activity_id=activity_id, tag=tag))
    db.commit()


def _tags_of(db: Session, activity_id: int) -> list[str]:
    return sorted(db.execute(select(ActivityTag.tag).where(ActivityTag.activity_id == activity_id)).scalars())


class TestSchema:
    def test_canonical_order_is_race_workout_long_run_then_nsm(self):
        assert [t.value for t in ActivityTagKey] == [
            "race",
            "workout",
            "long_run",
            "nsm_short",
            "nsm_medium",
            "nsm_long",
            "daniels_2q",
        ]
        assert sort_tags({t.value for t in reversed(ActivityTagKey)}) == list(ActivityTagKey)


class TestSetActivityTags:
    def test_sets_replaces_and_clears(self, db):
        db.add(_activity(1))
        db.commit()

        result = tags_crud.set_activity_tags(1, ["long_run", "race", "race"], OWNER, db)
        assert result.tags == [ActivityTagKey.RACE, ActivityTagKey.LONG_RUN]
        assert _tags_of(db, 1) == ["long_run", "race"]

        result = tags_crud.set_activity_tags(1, ["workout", "race"], OWNER, db)
        assert result.tags == [ActivityTagKey.RACE, ActivityTagKey.WORKOUT]
        assert _tags_of(db, 1) == ["race", "workout"]

        assert tags_crud.set_activity_tags(1, [], OWNER, db).tags == []
        assert _tags_of(db, 1) == []

    def test_every_tag_at_once(self, db):
        db.add(_activity(1))
        db.commit()

        result = tags_crud.set_activity_tags(1, [t.value for t in reversed(ActivityTagKey)], OWNER, db)
        assert result.tags == list(ActivityTagKey)
        assert _tags_of(db, 1) == sorted(t.value for t in ActivityTagKey)

    def test_kept_tags_keep_their_created_at(self, db):
        db.add(_activity(1))
        db.commit()
        db.add(ActivityTag(activity_id=1, tag="race", created_at=datetime(2020, 1, 1, tzinfo=UTC)))
        db.commit()

        tags_crud.set_activity_tags(1, ["race", "workout"], OWNER, db)

        kept = db.execute(select(ActivityTag).where(ActivityTag.tag == "race")).scalar_one()
        assert kept.created_at.year == 2020

    @pytest.mark.parametrize("user_id", [FOLLOWER, STRANGER])
    def test_only_the_owner_may_change_tags(self, db, user_id):
        db.add(_activity(1, visibility=0))
        db.commit()
        _tag(db, 1, "race")

        with pytest.raises(HTTPException) as err:
            tags_crud.set_activity_tags(1, ["workout"], user_id, db)

        assert err.value.status_code == 404
        assert _tags_of(db, 1) == ["race"]

    def test_unknown_activity_is_404(self, db):
        with pytest.raises(HTTPException) as err:
            tags_crud.set_activity_tags(99, ["race"], OWNER, db)
        assert err.value.status_code == 404

    def test_db_error_rolls_back_and_is_500(self, mock_db):
        mock_db.execute.side_effect = SQLAlchemyError("boom")
        with pytest.raises(HTTPException) as err:
            tags_crud.set_activity_tags(1, ["race"], OWNER, mock_db)
        assert err.value.status_code == 500
        mock_db.rollback.assert_called_once()


class TestVisibility:
    """Tags follow the activity's visibility; no separate privacy flag."""

    @pytest.fixture
    def tagged(self, db):
        db.add_all(
            [
                _activity(1, visibility=0),  # public
                _activity(2, visibility=1),  # followers
                _activity(3, visibility=2),  # private
                _activity(4, visibility=0, is_hidden=True),
                _activity(5, visibility=0),  # public, untagged
            ]
        )
        db.add(followers_models.Follower(follower_id=FOLLOWER, followee_id=OWNER, status="accepted"))
        db.commit()
        for activity_id in (1, 2, 3, 4):
            _tag(db, activity_id, "race")
        return db

    @staticmethod
    def _ids(result) -> list[int]:
        return [entry.activity_id for entry in result]

    def test_owner_sees_all_own_activities(self, tagged):
        result = tags_crud.get_visible_activities_tags([1, 2, 3, 4, 5], OWNER, tagged)
        assert self._ids(result) == [1, 2, 3, 4, 5]
        assert result[0].tags == [ActivityTagKey.RACE]
        assert result[4].tags == []

    def test_accepted_follower_sees_public_and_followers(self, tagged):
        assert self._ids(tags_crud.get_visible_activities_tags([1, 2, 3, 4, 5], FOLLOWER, tagged)) == [1, 2, 5]

    def test_stranger_sees_only_public(self, tagged):
        assert self._ids(tags_crud.get_visible_activities_tags([1, 2, 3, 4, 5], STRANGER, tagged)) == [1, 5]

    def test_unknown_ids_and_duplicates(self, tagged):
        assert self._ids(tags_crud.get_visible_activities_tags([5, 1, 5, 99], STRANGER, tagged)) == [5, 1]

    @patch("homelab.activity_tags.crud.server_settings_integration.public_shareable_links_enabled")
    def test_public_link_sees_only_public(self, mock_settings, tagged):
        mock_settings.return_value = True
        assert self._ids(tags_crud.get_public_activities_tags([1, 2, 3, 4], tagged)) == [1]

    @patch("homelab.activity_tags.crud.server_settings_integration.public_shareable_links_enabled")
    def test_public_links_disabled_sees_nothing(self, mock_settings, tagged):
        mock_settings.return_value = False
        assert tags_crud.get_public_activities_tags([1], tagged) == []

    def test_db_errors_are_500(self, mock_db):
        mock_db.execute.side_effect = SQLAlchemyError("boom")
        with pytest.raises(HTTPException) as err:
            tags_crud.get_visible_activities_tags([1], OWNER, mock_db)
        assert err.value.status_code == 500
        with (
            patch(
                "homelab.activity_tags.crud.server_settings_integration.public_shareable_links_enabled",
                return_value=True,
            ),
            pytest.raises(HTTPException) as err,
        ):
            tags_crud.get_public_activities_tags([1], mock_db)
        assert err.value.status_code == 500


class TestListFilter:
    """The upstream list and count queries keep activities with ALL tags."""

    @pytest.fixture
    def tagged(self, db):
        db.add_all([_activity(i) for i in range(1, 6)])
        db.add(_activity(6, user_id=STRANGER))
        db.commit()
        _tag(db, 1, "race", "long_run")
        _tag(db, 2, "race")
        _tag(db, 3, "long_run", "workout")
        _tag(db, 4, "race", "long_run", "workout")
        _tag(db, 5, "workout", "nsm_short", "daniels_2q")
        _tag(db, 6, "race")  # another user's
        return db

    @pytest.fixture(autouse=True)
    def _plain_serialization(self):
        # Serialization is not under test; return the ORM rows themselves.
        with (
            patch(
                "modules.activities.activity.crud.activity_serializers.serialize_and_mask",
                side_effect=lambda rows, **_: rows,
            ),
        ):
            yield

    @pytest.mark.parametrize(
        ("tags", "expected"),
        [
            (["race"], [4, 2, 1]),
            (["race", "long_run"], [4, 1]),
            (["long_run", "race", "race"], [4, 1]),
            (["race", "long_run", "workout"], [4]),
            (["workout"], [5, 4, 3]),
            (["nsm_short"], [5]),
            (["nsm_short", "workout"], [5]),
            (["nsm_short", "race"], []),
            (["daniels_2q"], [5]),
            (None, [5, 4, 3, 2, 1]),
            ([], [5, 4, 3, 2, 1]),
        ],
    )
    def test_list_and_count_use_and_semantics(self, tagged, tags, expected):
        page = activities_crud.get_user_activities_with_pagination(
            OWNER, tagged, page_number=1, num_records=50, user_is_owner=True, tags=tags
        )
        listed = activities_crud.get_user_activities(OWNER, tagged, user_is_owner=True, tags=tags)
        counted = activities_crud.count_user_activities(OWNER, tagged, user_is_owner=True, tags=tags)

        assert [a.id for a in page] == expected
        assert [a.id for a in listed] == expected
        assert counted == len(expected)

    def test_filter_combines_with_other_filters_and_pages(self, tagged):
        page = activities_crud.get_user_activities_with_pagination(
            OWNER,
            tagged,
            page_number=2,
            num_records=1,
            user_is_owner=True,
            tags=["race"],
            sort_by="start_time",
            sort_order="asc",
        )
        assert [a.id for a in page] == [2]

    def test_no_match_returns_empty(self, tagged):
        assert activities_crud.get_user_activities(5, tagged, user_is_owner=True, tags=["race"]) == []
        assert activities_crud.count_user_activities(5, tagged, user_is_owner=True, tags=["race"]) == 0

    def test_apply_tag_filter_is_a_noop_without_tags(self):
        stmt = select(activities_models.Activity)
        assert tags_filters.apply_tag_filter(stmt, None) is stmt
        assert tags_filters.apply_tag_filter(stmt, []) is stmt


def _build_app(mock_db, user_id: int = OWNER) -> FastAPI:
    import core.database as core_db
    import modules.activities.activity.router as activity_router
    import modules.auth.dependencies as auth_deps
    from homelab.activity_tags import public_router, router

    app = FastAPI()
    app.include_router(router.router, prefix="/homelab/activity_tags")
    app.include_router(public_router.router, prefix="/public/homelab/activity_tags")
    app.include_router(activity_router.router, prefix="/activities")
    app.dependency_overrides[auth_deps.check_scopes] = lambda: None
    app.dependency_overrides[auth_deps.get_sub_from_access_token] = lambda: user_id
    app.dependency_overrides[core_db.get_db] = lambda: mock_db
    return app


class TestRoutes:
    @patch("homelab.activity_tags.crud.get_visible_activities_tags", return_value=[])
    def test_batch_get_passes_ids_and_requester(self, mock_get, mock_db):
        resp = TestClient(_build_app(mock_db, user_id=7)).get("/homelab/activity_tags?activity_id=3&activity_id=5")
        assert resp.status_code == 200
        mock_get.assert_called_once_with([3, 5], 7, mock_db)

    @pytest.mark.parametrize(
        "query",
        ["", "?activity_id=-1", "?activity_id=x", "?" + "&".join(f"activity_id={i}" for i in range(101))],
    )
    def test_batch_get_validates_ids(self, mock_db, query):
        assert TestClient(_build_app(mock_db)).get(f"/homelab/activity_tags{query}").status_code == 422

    @patch("homelab.activity_tags.crud.get_public_activities_tags", return_value=[])
    def test_public_batch_get(self, mock_get, mock_db):
        resp = TestClient(_build_app(mock_db)).get("/public/homelab/activity_tags?activity_id=4")
        assert resp.status_code == 200
        mock_get.assert_called_once_with([4], mock_db)

    @patch("homelab.activity_tags.crud.set_activity_tags")
    def test_put_sets_tags_as_the_token_user(self, mock_set, mock_db):
        from homelab.activity_tags.schema import ActivityTagsRead

        mock_set.return_value = ActivityTagsRead(activity_id=4, tags=[ActivityTagKey.RACE])
        resp = TestClient(_build_app(mock_db, user_id=7)).put("/homelab/activity_tags/4", json={"tags": ["race"]})
        assert resp.status_code == 200
        assert resp.json() == {"activity_id": 4, "tags": ["race"]}
        mock_set.assert_called_once_with(4, [ActivityTagKey.RACE], 7, mock_db)

    @pytest.mark.parametrize(
        "body",
        [{"tags": ["tempo"]}, {"tags": ["race"] * 8}, {}, {"tags": [], "extra": 1}],
    )
    def test_put_validates_body(self, mock_db, body):
        assert TestClient(_build_app(mock_db)).put("/homelab/activity_tags/4", json=body).status_code == 422

    @pytest.mark.parametrize("path", ["/activities", "/activities/users/1"])
    def test_list_endpoints_pass_tags_to_page_and_total(self, mock_db, path):
        # Upstream v0.20 answers the list and its total in one paged call.
        with (
            patch("modules.activities.activity.crud.get_user_activities_with_pagination", return_value=[]) as listed,
            patch("modules.activities.activity.crud.count_user_activities", return_value=0) as counted,
            patch("modules.activities.activity.service._followees_of", return_value=[]),
        ):
            resp = TestClient(_build_app(mock_db)).get(f"{path}?tag=race&tag=long_run")
        assert resp.status_code == 200
        assert listed.call_args.kwargs["tags"] == [ActivityTagKey.RACE, ActivityTagKey.LONG_RUN]
        assert counted.call_args.kwargs["tags"] == [ActivityTagKey.RACE, ActivityTagKey.LONG_RUN]

    def test_list_endpoints_reject_unknown_tags(self, mock_db):
        client = TestClient(_build_app(mock_db))
        assert client.get("/activities?tag=tempo").status_code == 422
        assert client.get("/activities/users/1?tag=tempo").status_code == 422

    def test_fork_routes_are_registered_in_the_api_router(self):
        from api import router as api_router

        app = FastAPI()
        app.include_router(api_router)
        paths = app.openapi()["paths"]
        assert set(paths["/api/v1/homelab/activity_tags"]) == {"get"}
        assert set(paths["/api/v1/homelab/activity_tags/{activity_id}"]) == {"put"}
        assert set(paths["/api/v1/public/homelab/activity_tags"]) == {"get"}
