"""OSC 0022: superadmin sets / clears a version's display label (same-round alternates "v2 · A midair")."""
import uuid
from types import SimpleNamespace


def _as(sa):
    from apps.api.main import app
    from apps.api.middleware.auth import get_current_user
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=uuid.uuid4(), is_superadmin=sa)
    return app, get_current_user


def test_only_a_superadmin_can_label(client):
    app, dep = _as(False)
    try:
        r = client.put(f"/osc/admin/versions/{uuid.uuid4()}/label", json={"label": "v2 · A"})
    finally:
        app.dependency_overrides.pop(dep, None)
    assert r.status_code == 403


def test_label_is_written_and_echoed(client, mock_db):
    mock_db.first.return_value = SimpleNamespace(id=uuid.uuid4())
    app, dep = _as(True)
    try:
        r = client.put(f"/osc/admin/versions/{uuid.uuid4()}/label", json={"label": "  v2 · B lastair "})
    finally:
        app.dependency_overrides.pop(dep, None)
    assert r.status_code == 200 and r.json()["label"] == "v2 · B lastair"
    assert "INSERT INTO osc_version_labels" in str(mock_db.execute.call_args[0][0])


def test_an_empty_label_clears_it(client, mock_db):
    mock_db.first.return_value = SimpleNamespace(id=uuid.uuid4())
    app, dep = _as(True)
    try:
        r = client.put(f"/osc/admin/versions/{uuid.uuid4()}/label", json={"label": ""})
    finally:
        app.dependency_overrides.pop(dep, None)
    assert r.status_code == 200 and r.json()["label"] is None
    assert "DELETE FROM osc_version_labels" in str(mock_db.execute.call_args[0][0])
