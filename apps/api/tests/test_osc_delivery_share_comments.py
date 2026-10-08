"""OSC 0017: a delivery (view-only) link shows no comments; a link without version history shows only the
served (latest) version's comments, never older versions' notes."""
import uuid
from types import SimpleNamespace
from unittest.mock import patch

from apps.api.models.share import SharePermission

M = "apps.api.routers.comments"


def _link(perm, show_versions=True):
    return SimpleNamespace(id=uuid.uuid4(), asset_id=uuid.uuid4(), permission=perm, show_versions=show_versions)


def test_a_view_only_link_returns_no_comments(client):
    link = _link(SharePermission.view)
    with patch(f"{M}.validate_share_link_with_session", return_value=link), \
         patch(f"{M}._get_asset", return_value=SimpleNamespace(id=link.asset_id)), \
         patch(f"{M}.validate_asset_in_share"), \
         patch(f"{M}._build_comment_responses_batched") as build:
        r = client.get("/share/tok/comments")
    assert r.status_code == 200 and r.json() == []
    build.assert_not_called()


def test_a_link_without_version_history_ignores_a_requested_old_version(client, mock_db):
    link = _link(SharePermission.comment, show_versions=False)
    latest = SimpleNamespace(id=uuid.uuid4())
    old = uuid.uuid4()
    mock_db.order_by.return_value = mock_db  # the fixture doesn't chain order_by
    mock_db.first.return_value = latest
    mock_db.all.return_value = []
    with patch(f"{M}.validate_share_link_with_session", return_value=link), \
         patch(f"{M}._get_asset", return_value=SimpleNamespace(id=link.asset_id)), \
         patch(f"{M}.validate_asset_in_share"), \
         patch(f"{M}._build_comment_responses_batched", return_value=[]) as build:
        r = client.get(f"/share/tok/comments?version_id={old}")
    assert r.status_code == 200
    # The requested version was dropped and the LATEST ready version was looked up instead.
    assert mock_db.first.called
    assert mock_db.order_by.called
