"""Homelab fork: the total distance of every gear, for the gear list."""

from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

import auth.dependencies as auth_deps
import core.database as core_db
import gears.gear.crud as gears_crud
import gears.gear.models as gears_models
from homelab.gear_mileage import crud as mileage_crud
from homelab.gear_mileage import router as mileage_router
from homelab.gear_mileage.schema import GearMileageRead
from tests._helpers.db import create_sqlite_session
from tests.homelab.test_training_log import OTHER, OWNER, _activity

START = datetime(2026, 10, 13, 7, tzinfo=UTC)


@pytest.fixture
def db() -> Iterator[Session]:
    """SQLite session with upstream's tables."""
    session = create_sqlite_session()
    try:
        yield session
    finally:
        session.close()
        session.bind.dispose()


def _gear(gear_id: int, user_id: int = OWNER, initial_kms: str = "0") -> gears_models.Gear:
    return gears_models.Gear(
        id=gear_id,
        nickname=f"Shoe {gear_id}",
        gear_type=2,
        user_id=user_id,
        created_at=START,
        active=True,
        initial_kms=Decimal(initial_kms),
    )


def _mileage(user_id: int, db: Session) -> dict[int, float]:
    return {row.gear_id: row.total_distance for row in mileage_crud.get_gear_mileage(user_id, db)}


class TestGetGearMileage:
    def test_sums_each_gears_activities_and_initial_distance(self, db):
        db.add_all(
            [
                _gear(1, initial_kms="100"),
                _gear(2),
                _activity(1, START, gear_id=1, distance=5000),
                _activity(2, START, gear_id=1, distance=7000),
                _activity(3, START, gear_id=2, distance=3000),
                _activity(4, START, gear_id=None, distance=9000),
            ]
        )
        db.commit()

        assert _mileage(OWNER, db) == {1: 112000, 2: 3000}

    def test_gear_with_no_activities_keeps_its_initial_distance(self, db):
        db.add_all([_gear(1, initial_kms="42.5"), _gear(2)])
        db.commit()

        assert _mileage(OWNER, db) == {1: 42500, 2: 0}

    def test_only_the_users_gear(self, db):
        db.add_all(
            [
                _gear(1),
                _gear(2, user_id=OTHER),
                _activity(1, START, gear_id=1, distance=5000),
                _activity(2, START, gear_id=2, distance=6000, user_id=OTHER),
            ]
        )
        db.commit()

        assert _mileage(OWNER, db) == {1: 5000}

    def test_matches_the_gear_detail_total(self, db):
        db.add_all(
            [
                _gear(1, initial_kms="12.25"),
                _activity(1, START, gear_id=1, distance=5000),
                _activity(2, START, gear_id=1, distance=7000, is_hidden=True),
            ]
        )
        db.commit()

        activities_distance = gears_crud.get_gear_activity_stats(1, db)["total_distance"]
        assert _mileage(OWNER, db) == {1: activities_distance + 12250}


class TestRoute:
    def test_returns_the_requesters_mileage(self):
        mock_db = MagicMock(spec=Session)
        app = FastAPI()
        app.include_router(mileage_router.router, prefix="/homelab/gear_mileage")
        app.dependency_overrides[auth_deps.check_scopes] = lambda: None
        app.dependency_overrides[auth_deps.get_sub_from_access_token] = lambda: 7
        app.dependency_overrides[core_db.get_db] = lambda: mock_db

        with patch(
            "homelab.gear_mileage.crud.get_gear_mileage",
            return_value=[GearMileageRead(gear_id=1, total_distance=5000)],
        ) as mock_mileage:
            resp = TestClient(app).get("/homelab/gear_mileage")

        assert resp.status_code == 200
        assert resp.json() == [{"gear_id": 1, "total_distance": 5000}]
        mock_mileage.assert_called_once_with(7, mock_db)
