"""OSC 0019: share kinds (review / delivery). Mock-based: the inference rule, the presets, the slate
guard (409 vs force) and the editor gate. The upsert SQL itself is checked live."""
import uuid
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

from apps.api.models.share import SharePermission
from apps.api.routers.osc_share_meta import SLATE_TC, infer_kind

M = "apps.api.routers.osc_share_meta"


def _user(sa):
    return SimpleNamespace(id=uuid.uuid4(), is_superadmin=sa, email="x@t.local", name="x")


@contextmanager
def _as(user):
    from apps.api.main import app
    from apps.api.middleware.auth import get_current_user
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def _link(perm=SharePermission.comment, dl=False, sv=True):
    return SimpleNamespace(id=uuid.uuid4(), asset_id=uuid.uuid4(), folder_id=None, project_id=uuid.uuid4(),
                           permission=perm, allow_download=dl, show_versions=sv, deleted_at=None)


def test_inference_rule():
    assert infer_kind(SharePermission.view, True) == "delivery"
    assert infer_kind("view", True) == "delivery"
    assert infer_kind(SharePermission.view, False) == "review"
    assert infer_kind(SharePermission.comment, True) == "review"
    assert infer_kind(SharePermission.approve, False) == "review"


def test_project_map_uses_rows_and_infers_the_rest(client, mock_db):
    stored, bare = _link(), _link(SharePermission.view, dl=True)
    mock_db.outerjoin.return_value = mock_db
    mock_db.all.return_value = [stored, bare]
    mock_db.execute.return_value.fetchall.return_value = [(stored.id, "delivery", "Acme v3 for Jo")]
    with _as(_user(True)):
        r = client.get(f"/osc/projects/{uuid.uuid4()}/share-meta")
    assert r.status_code == 200
    body = r.json()
    assert body[str(stored.id)] == {"kind": "delivery", "internal_label": "Acme v3 for Jo", "inferred": False}
    assert body[str(bare.id)] == {"kind": "delivery", "internal_label": None, "inferred": True}


def test_delivery_preset_is_applied(client, mock_db):
    link = _link()
    mock_db.first.return_value = link
    mock_db.execute.return_value.fetchall.return_value = []
    with _as(_user(True)), patch(f"{M}.slated_items", return_value=[]):
        r = client.put(f"/osc/share-links/{link.id}/meta", json={"kind": "delivery", "internal_label": " Final "})
    assert r.status_code == 200
    assert r.json() == {"kind": "delivery", "internal_label": "Final", "permission": "view",
                        "allow_download": True, "show_versions": False}
    assert link.permission == SharePermission.view and link.allow_download and not link.show_versions
    mock_db.commit.assert_called()


def test_review_preset_turns_history_back_on_only_after_a_delivery(client, mock_db):
    link = _link(SharePermission.view, dl=True, sv=False)
    mock_db.first.return_value = link
    mock_db.execute.return_value.fetchall.return_value = [(link.id, "delivery", "keep me")]
    with _as(_user(True)):
        r = client.put(f"/osc/share-links/{link.id}/meta", json={"kind": "review"})
    assert r.status_code == 200
    assert r.json() == {"kind": "review", "internal_label": "keep me", "permission": "comment",
                        "allow_download": False, "show_versions": True}

    other = _link(SharePermission.comment, dl=False, sv=False)
    mock_db.first.return_value = other
    mock_db.execute.return_value.fetchall.return_value = [(other.id, "review", None)]
    with _as(_user(True)):
        r = client.put(f"/osc/share-links/{other.id}/meta", json={"kind": "review"})
    assert r.json()["show_versions"] is False


def test_slated_master_is_refused_unless_forced(client, mock_db):
    link = _link()
    mock_db.first.return_value = link
    mock_db.order_by.return_value = mock_db
    mock_db.execute.return_value.fetchall.return_value = []
    asset = SimpleNamespace(id=uuid.uuid4(), name="Brand Film :60")
    version = SimpleNamespace(id=uuid.uuid4())
    with _as(_user(True)), patch(f"{M}.served_assets", return_value=[asset]), \
         patch(f"{M}.latest_ready_version", return_value=version), \
         patch(f"{M}.source_tc_for_version", return_value={"start_tc": SLATE_TC, "fps": 24.0, "start_frames": 1}):
        r = client.put(f"/osc/share-links/{link.id}/meta", json={"kind": "delivery"})
        assert r.status_code == 409
        assert r.json()["slated"] == ["Brand Film :60"] and "slate" in r.json()["detail"]
        assert link.permission == SharePermission.comment  # nothing applied
        mock_db.commit.assert_not_called()

        r = client.put(f"/osc/share-links/{link.id}/meta", json={"kind": "delivery", "force": True})
    assert r.status_code == 200 and r.json()["permission"] == "view"


def test_clean_master_passes_the_guard(client, mock_db):
    link = _link()
    mock_db.first.return_value = link
    mock_db.execute.return_value.fetchall.return_value = []
    asset = SimpleNamespace(id=uuid.uuid4(), name="Brand Film :60")
    with _as(_user(True)), patch(f"{M}.served_assets", return_value=[asset]), \
         patch(f"{M}.latest_ready_version", return_value=SimpleNamespace(id=uuid.uuid4())), \
         patch(f"{M}.source_tc_for_version", return_value={"start_tc": "01:00:00:00", "fps": 24.0, "start_frames": 1}):
        r = client.put(f"/osc/share-links/{link.id}/meta", json={"kind": "delivery"})
    assert r.status_code == 200


def test_a_non_editor_is_refused(client, mock_db):
    link = _link()
    mock_db.first.side_effect = [link, None]  # the link, then no project membership
    with _as(_user(False)):
        r = client.put(f"/osc/share-links/{link.id}/meta", json={"kind": "delivery"})
    assert r.status_code == 403

    mock_db.first.side_effect = None
    mock_db.first.return_value = None
    with _as(_user(False)):
        r = client.get(f"/osc/projects/{uuid.uuid4()}/share-meta")
    assert r.status_code == 403
