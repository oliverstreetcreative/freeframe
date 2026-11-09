"""`POST /projects/{id}/bulk-move` must not put a folder beneath its own subtree.

The folder branch of bulk-move computed the descendants of the TARGET and
refused a moved folder found among them. That is the wrong subtree: a cycle
forms when the target sits under the MOVED folder. So moving a parent into
its own child was accepted, the child became the parent's parent, and both
fell out of the tree (neither is reachable from a root). The same mistake
refused the harmless opposite, lifting a nested folder up into one of its
ancestors. The route now checks each moved folder's own descendants, as
`PATCH /folders/{id}` already did, and validates every folder before anything
moves, so a refused request leaves folders and assets exactly where they were.

These go through the real HTTP route against real PostgreSQL inside a
rolled-back transaction (#1074, PLAN.md I91).
"""
import uuid
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def tree(real_db):
    """Project with root/ -> parent/ -> child/ -> grandchild/, plus sibling/ and an asset."""
    from apps.api.models.asset import Asset, AssetType
    from apps.api.models.folder import Folder
    from apps.api.models.project import Project, ProjectMember, ProjectRole, ProjectType
    from apps.api.models.user import User

    editor = User(email=f"bulk-move-{uuid.uuid4()}@t.local", name="editor")
    real_db.add(editor); real_db.flush()
    project = Project(name="bulk-move", project_type=ProjectType.personal, created_by=editor.id)
    real_db.add(project); real_db.flush()
    real_db.add(ProjectMember(project_id=project.id, user_id=editor.id, role=ProjectRole.editor))
    real_db.flush()

    def folder(name, parent=None):
        f = Folder(project_id=project.id, name=name, created_by=editor.id,
                   parent_id=parent.id if parent else None)
        real_db.add(f); real_db.flush()
        return f

    root = folder("root")
    parent = folder("parent", root)
    child = folder("child", parent)
    grandchild = folder("grandchild", child)
    sibling = folder("sibling", root)
    asset = Asset(project_id=project.id, name="clip", asset_type=AssetType.video,
                  created_by=editor.id, folder_id=sibling.id)
    real_db.add(asset); real_db.flush()
    return {"editor": editor, "project": project, "root": root, "parent": parent,
            "child": child, "grandchild": grandchild, "sibling": sibling, "asset": asset}


@pytest.fixture
def http(real_db, tree):
    with patch("apps.api.services.s3_service.ensure_bucket_exists"), \
         patch("apps.api.services.s3_service.get_s3_client", return_value=MagicMock()):
        from fastapi.testclient import TestClient
        from apps.api.database import get_db
        from apps.api.main import app
        from apps.api.middleware.auth import get_current_user

        app.dependency_overrides[get_db] = lambda: real_db
        app.dependency_overrides[get_current_user] = lambda: tree["editor"]
        try:
            yield TestClient(app, raise_server_exceptions=False)
        finally:
            app.dependency_overrides.clear()


def _bulk_move(http, tree, folders=(), assets=(), target=None):
    return http.post(
        f"/projects/{tree['project'].id}/bulk-move",
        json={
            "folder_ids": [str(f.id) for f in folders],
            "asset_ids": [str(a.id) for a in assets],
            "target_folder_id": str(target.id) if target else None,
        },
    )


def _layout(real_db, tree):
    """Every folder's parent and the asset's folder, re-read from the database."""
    from apps.api.models.asset import Asset
    from apps.api.models.folder import Folder

    real_db.expire_all()
    rows = real_db.query(Folder.id, Folder.parent_id).filter(
        Folder.project_id == tree["project"].id).all()
    asset_folder = real_db.query(Asset.folder_id).filter(Asset.id == tree["asset"].id).scalar()
    return {fid: pid for fid, pid in rows}, asset_folder


def _reachable_from_roots(layout):
    parents, _ = layout
    children = {}
    for fid, pid in parents.items():
        children.setdefault(pid, []).append(fid)
    seen, queue = set(), list(children.get(None, []))
    while queue:
        fid = queue.pop()
        seen.add(fid)
        queue.extend(children.get(fid, []))
    return seen == set(parents)


@pytest.mark.parametrize("descendant", ["child", "grandchild"])
def test_parent_cannot_move_beneath_its_own_descendant(real_db, tree, http, descendant):
    before = _layout(real_db, tree)

    response = _bulk_move(http, tree, folders=[tree["parent"]], target=tree[descendant])

    assert response.status_code == 400, response.text
    assert "into itself or a subfolder" in response.json()["detail"]
    after = _layout(real_db, tree)
    assert after == before
    assert _reachable_from_roots(after)


def test_folder_cannot_move_into_itself(real_db, tree, http):
    before = _layout(real_db, tree)

    response = _bulk_move(http, tree, folders=[tree["child"]], target=tree["child"])

    assert response.status_code == 400, response.text
    assert _layout(real_db, tree) == before


def test_refused_batch_moves_nothing(real_db, tree, http):
    """One bad folder refuses the whole request; the valid folder and the asset stay put."""
    before = _layout(real_db, tree)

    response = _bulk_move(http, tree, folders=[tree["sibling"], tree["parent"]],
                          assets=[tree["asset"]], target=tree["grandchild"])

    assert response.status_code == 400, response.text
    assert _layout(real_db, tree) == before


def test_nested_folder_can_move_up_into_an_ancestor(real_db, tree, http):
    """The old target-descendant check refused this harmless move."""
    response = _bulk_move(http, tree, folders=[tree["grandchild"]], target=tree["root"])

    assert response.status_code == 200, response.text
    parents, _ = _layout(real_db, tree)
    assert parents[tree["grandchild"].id] == tree["root"].id
    assert _reachable_from_roots((parents, None))


def test_unrelated_folder_and_asset_move_together(real_db, tree, http):
    response = _bulk_move(http, tree, folders=[tree["sibling"]], assets=[tree["asset"]],
                          target=tree["child"])

    assert response.status_code == 200, response.text
    assert response.json() == {"ok": True, "moved_assets": 1, "moved_folders": 1}
    parents, asset_folder = _layout(real_db, tree)
    assert parents[tree["sibling"].id] == tree["child"].id
    assert asset_folder == tree["child"].id
    assert _reachable_from_roots((parents, None))


def test_folder_can_move_to_project_root(real_db, tree, http):
    response = _bulk_move(http, tree, folders=[tree["child"]], target=None)

    assert response.status_code == 200, response.text
    parents, _ = _layout(real_db, tree)
    assert parents[tree["child"].id] is None
    assert parents[tree["grandchild"].id] == tree["child"].id
