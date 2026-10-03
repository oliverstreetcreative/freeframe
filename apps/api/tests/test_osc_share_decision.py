"""OSC 0010: client approval from a share link: the guard rails (the happy path is checked live)."""
import uuid
from types import SimpleNamespace
from unittest.mock import patch

from apps.api.models.share import SharePermission

M = "apps.api.routers.osc_share_decision"


def _link(perm):
    return SimpleNamespace(id=uuid.uuid4(), asset_id=uuid.uuid4(), permission=perm)


def test_a_comment_only_link_cannot_approve(client):
    with patch(f"{M}.validate_share_link_with_session", return_value=_link(SharePermission.comment)):
        r = client.post("/share/tok/decision", json={"decision": "approved", "guest_name": "A", "guest_email": "a@x.com"})
    assert r.status_code == 403


def test_unknown_decision_is_refused(client):
    with patch(f"{M}.validate_share_link_with_session", return_value=_link(SharePermission.approve)):
        r = client.post("/share/tok/decision", json={"decision": "maybe", "guest_name": "A", "guest_email": "a@x.com"})
    assert r.status_code == 400


def test_a_guest_must_say_who_they_are(client, mock_db):
    asset = SimpleNamespace(id=uuid.uuid4(), name="Spot", deleted_at=None, project_id=uuid.uuid4())
    version = SimpleNamespace(id=uuid.uuid4())
    mock_db.first.side_effect = [asset, version]
    with patch(f"{M}.validate_share_link_with_session", return_value=_link(SharePermission.approve)), \
         patch(f"{M}.validate_asset_in_share"):
        r = client.post("/share/tok/decision", json={"decision": "approved"})
    assert r.status_code == 400 and "guest_name" in r.text
