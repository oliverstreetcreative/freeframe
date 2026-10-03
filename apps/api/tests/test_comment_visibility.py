"""Internal comments are enforced server-side.

Root cause of the leak: the share-link comment route's schema had no `visibility` field, so a
signed-in project editor choosing "Internal" on a share page was silently saved as public. These
tests pin the rule in services/comment_visibility.py and the schema fix.
"""
import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from apps.api.models.project import ProjectRole
from apps.api.schemas.comment import GuestCommentCreate
from apps.api.services import comment_visibility as ov

PID = uuid.uuid4()


def user(superadmin=False):
    return SimpleNamespace(id=uuid.uuid4(), is_superadmin=superadmin)


def member(role):
    return SimpleNamespace(role=role) if role else None


@pytest.mark.parametrize("role,staff", [
    (ProjectRole.owner, True), (ProjectRole.editor, True),
    (ProjectRole.reviewer, False), (ProjectRole.viewer, False), (None, False),
])
def test_is_staff_by_role(role, staff):
    with patch.object(ov, "get_project_member", return_value=member(role)):
        assert ov.is_staff(None, PID, user()) is staff


def test_superadmin_is_staff_and_guest_is_not():
    with patch.object(ov, "get_project_member", return_value=None):
        assert ov.is_staff(None, PID, user(superadmin=True)) is True
    assert ov.is_staff(None, PID, None) is False


def test_staff_internal_is_kept():
    with patch.object(ov, "get_project_member", return_value=member(ProjectRole.editor)):
        assert ov.resolve_visibility(None, PID, user(), "internal") == "internal"
        assert ov.resolve_visibility(None, PID, user(), "INTERNAL ") == "internal"


@pytest.mark.parametrize("role", [ProjectRole.reviewer, ProjectRole.viewer, None])
def test_non_staff_internal_is_refused_never_downgraded(role):
    with patch.object(ov, "get_project_member", return_value=member(role)):
        with pytest.raises(HTTPException) as e:
            ov.resolve_visibility(None, PID, user(), "internal")
    assert e.value.status_code == 403


def test_guest_internal_is_refused():
    with pytest.raises(HTTPException) as e:
        ov.resolve_visibility(None, PID, None, "internal")
    assert e.value.status_code == 403


def test_missing_means_public_and_junk_is_refused():
    assert ov.resolve_visibility(None, PID, None, None) == "public"
    assert ov.resolve_visibility(None, PID, None, "public") == "public"
    with pytest.raises(HTTPException) as e:
        ov.resolve_visibility(None, PID, None, "secret")
    assert e.value.status_code == 400


def test_reply_under_internal_parent_is_internal_for_staff_and_refused_for_others():
    parent = SimpleNamespace(visibility="internal")
    with patch.object(ov, "get_project_member", return_value=member(ProjectRole.owner)):
        assert ov.resolve_visibility(None, PID, user(), "public", parent) == "internal"
    with patch.object(ov, "get_project_member", return_value=member(ProjectRole.reviewer)):
        with pytest.raises(HTTPException):
            ov.resolve_visibility(None, PID, user(), "public", parent)


def test_share_route_schema_now_carries_visibility():
    # Before the fix pydantic dropped this field on the floor.
    body = GuestCommentCreate(body="x", visibility="internal")
    assert body.visibility == "internal"
    assert GuestCommentCreate(body="x").visibility == "public"
