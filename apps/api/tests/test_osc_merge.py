"""OSC 0016: merging items into one stacked item. The stack order is pure and tested here; the guards are
tested through the route with a mocked DB (the row moves themselves are verified live, on a TEST project)."""
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from apps.api.routers.osc_merge import plan_order

T0 = datetime(2026, 10, 3, 20, 0)


def test_the_stack_is_oldest_upload_first():
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    rows = [(c, T0 + timedelta(hours=3), False, 0, 1),   # newest, from a source
            (a, T0, True, -1, 1),                         # target's v1
            (b, T0 + timedelta(hours=1), True, -1, 2)]    # target's v2
    assert plan_order(rows) == [(a, 1), (b, 2), (c, 3)]


def test_ties_keep_the_target_first_then_sources_in_the_order_given():
    t, s1, s2 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    rows = [(s2, T0, False, 1, 1), (s1, T0, False, 0, 1), (t, T0, True, -1, 5)]
    assert plan_order(rows) == [(t, 1), (s1, 2), (s2, 3)]


def test_missing_dates_sort_first_and_never_crash():
    a, b = uuid.uuid4(), uuid.uuid4()
    assert plan_order([(a, T0, True, -1, 1), (b, None, False, 0, 1)]) == [(b, 1), (a, 2)]


def _user(sa):
    return SimpleNamespace(id=uuid.uuid4(), is_superadmin=sa, email="x@t.local", name="x")


def test_only_a_superadmin_can_merge(client):
    from apps.api.main import app
    from apps.api.middleware.auth import get_current_user
    app.dependency_overrides[get_current_user] = lambda: _user(False)
    try:
        r = client.post("/osc/admin/merge", json={"target_asset_id": str(uuid.uuid4()), "sources": []})
    finally:
        app.dependency_overrides.pop(get_current_user, None)
    assert r.status_code == 403


def test_a_source_a_client_link_serves_is_refused(client, mock_db):
    from apps.api.main import app
    from apps.api.middleware.auth import get_current_user
    pid = uuid.uuid4()
    target = SimpleNamespace(id=uuid.uuid4(), project_id=pid, name="T", folder_id=None, deleted_at=None)
    src = SimpleNamespace(id=uuid.uuid4(), project_id=pid, name="S", folder_id=None, deleted_at=None)
    mock_db.first.side_effect = [target, src]
    app.dependency_overrides[get_current_user] = lambda: _user(True)
    try:
        with patch("apps.api.routers.osc_merge._enabled_links_serving", return_value=["Client delivery (TWwaeV7i)"]):
            r = client.post("/osc/admin/merge", json={"target_asset_id": str(target.id),
                                                      "sources": [{"asset_id": str(src.id)}], "dry_run": True})
    finally:
        app.dependency_overrides.pop(get_current_user, None)
    assert r.status_code == 409 and "client link" in r.text
