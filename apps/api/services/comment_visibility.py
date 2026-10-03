"""Internal-comment enforcement.

The rule, enforced on the SERVER whatever the UI sends:
  * Only STAFF may write or read internal comments. Staff = a superadmin, or an owner/editor on
    the project. Reviewers/viewers (client accounts) and share-link guests are never staff.
  * A non-staff request for "internal" is REFUSED (403), never quietly saved as public. A silent
    downgrade is exactly how the leak happened.
  * A reply to an internal comment is internal, whatever was asked.
  * Unknown values are refused (400); missing means public.
"""
import uuid
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from ..models.project import ProjectRole
from ..models.user import User
from .permissions import get_project_member

STAFF_ROLES = (ProjectRole.owner, ProjectRole.editor)


def is_staff(db: Session, project_id: uuid.UUID, user: Optional[User]) -> bool:
    if user is None:
        return False
    if getattr(user, "is_superadmin", False):
        return True
    member = get_project_member(db, project_id, user.id)
    return bool(member and member.role in STAFF_ROLES)


def resolve_visibility(db: Session, project_id: uuid.UUID, user: Optional[User],
                       requested: Optional[str], parent=None) -> str:
    requested = (requested or "public").strip().lower()
    if requested not in ("public", "internal"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "visibility must be 'public' or 'internal'")
    if parent is not None and getattr(parent, "visibility", "public") == "internal":
        requested = "internal"
    if requested == "internal" and not is_staff(db, project_id, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Internal comments can only be posted by project editors or owners.")
    return requested
