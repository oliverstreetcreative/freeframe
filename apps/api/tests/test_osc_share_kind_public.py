"""OSC 0020: the recipient's page reads the link's kind (and nothing else) from a public endpoint."""
import uuid
from types import SimpleNamespace
from unittest.mock import patch

M = "apps.api.routers.osc_share_meta"


def _link(perm, dl):
    return SimpleNamespace(id=uuid.uuid4(), permission=perm, allow_download=dl)


def test_a_stored_kind_wins(client):
    link = _link("comment", False)
    with patch("apps.api.services.permissions.validate_share_link_with_session", return_value=link), \
         patch(f"{M}._meta_rows", return_value={str(link.id): ("delivery", "Staff-only label")}):
        r = client.get("/share/tok/osc-kind")
    assert r.status_code == 200 and r.json() == {"kind": "delivery"}  # never the internal label


def test_no_row_infers_from_the_link(client):
    with patch("apps.api.services.permissions.validate_share_link_with_session", return_value=_link("view", True)), \
         patch(f"{M}._meta_rows", return_value={}):
        assert client.get("/share/tok/osc-kind").json() == {"kind": "delivery"}
    with patch("apps.api.services.permissions.validate_share_link_with_session", return_value=_link("comment", False)), \
         patch(f"{M}._meta_rows", return_value={}):
        assert client.get("/share/tok/osc-kind").json() == {"kind": "review"}
