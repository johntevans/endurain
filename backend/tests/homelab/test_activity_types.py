"""Homelab fork: activity types the fork adds to upstream's mapping."""

from activities.activity.utils import ACTIVITY_ID_TO_NAME, ACTIVITY_NAME_TO_ID


def test_physical_therapy_has_a_fork_only_id():
    assert ACTIVITY_ID_TO_NAME[1001] == "Physical therapy"


def test_physical_therapy_resolves_by_name():
    for name in ("physical therapy", "physical_therapy", "physicaltherapy"):
        assert ACTIVITY_NAME_TO_ID[name] == 1001


def test_upstream_ids_stay_below_the_fork_range():
    # Upstream numbers its types sequentially; if it ever reaches 1001 the fork
    # type would be shadowed, so fail loudly on the merge that gets close.
    upstream_ids = [type_id for type_id in ACTIVITY_ID_TO_NAME if type_id != 1001]
    assert max(upstream_ids) < 1000
