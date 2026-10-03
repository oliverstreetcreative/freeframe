"""OSC 0010: a client approves (or requests changes) straight from a share link.

Upstream FreeFrame has an "approve" link permission, but the only approve route needs a signed-in
project member, and the share page has no approval UI at all. So a client holding just the link
Sam sent could comment but never say "approved". This adds:

  POST /share/{token}/decision  {decision: "approved"|"rejected", note?, asset_id?, version_id?,
                                 guest_name?, guest_email?}
    - only on a link whose permission is "approve" (403 otherwise)
    - identity: the signed-in user, else guest name + email (like a guest comment)
    - one decision per person per version (re-deciding replaces it)
    - visible to staff three ways: a public comment in the thread ("✅ Approved — Name" /
      "🔁 Changes requested — Name: note"), the link's activity log (approved/rejected), and the
      status pill (latest version: changes requested -> red, else approved -> green)
  GET  /share/{token}/decisions?asset_id=&version_id=  -> [{name, decision, at}] for that version
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..database import get_db
from ..middleware.auth import get_optional_user
from ..models.asset import Asset, AssetVersion, ProcessingStatus
from ..models.comment import Comment
from ..models.share import ShareActivityAction, ShareLinkActivity, SharePermission
from ..models.user import GuestUser, User
from ..services import event_service
from ..services.osc_status_rules import sync_status
from ..services.permissions import validate_asset_in_share, validate_share_link_with_session

router = APIRouter(tags=["osc_share_decision"])


class DecisionIn(BaseModel):
    decision: str
    note: Optional[str] = None
    asset_id: Optional[uuid.UUID] = None
    version_id: Optional[uuid.UUID] = None
    guest_name: Optional[str] = None
    guest_email: Optional[str] = None


def _resolve(db: Session, link, asset_id, version_id):
    target = link.asset_id or asset_id
    if not target:
        raise HTTPException(400, "asset_id is required for folder/project shares")
    asset = db.query(Asset).filter(Asset.id == target, Asset.deleted_at.is_(None)).first()
    if not asset:
        raise HTTPException(404, "Asset not found")
    validate_asset_in_share(db, link, asset)
    q = db.query(AssetVersion).filter(AssetVersion.asset_id == asset.id, AssetVersion.deleted_at.is_(None),
                                      AssetVersion.processing_status == ProcessingStatus.ready)
    version = q.filter(AssetVersion.id == version_id).first() if version_id else \
        q.order_by(AssetVersion.version_number.desc()).first()
    if not version:
        raise HTTPException(400, "No ready version for this asset")
    return asset, version


@router.post("/share/{token}/decision", status_code=201)
def share_decision(token: str, body: DecisionIn, share_session: Optional[str] = Query(None),
                   db: Session = Depends(get_db), current_user: Optional[User] = Depends(get_optional_user)):
    link = validate_share_link_with_session(db, token, share_session=share_session, current_user=current_user)
    if link.permission != SharePermission.approve:
        raise HTTPException(403, "This link doesn't allow approvals")
    decision = (body.decision or "").strip().lower()
    if decision not in ("approved", "rejected"):
        raise HTTPException(400, "decision must be 'approved' or 'rejected'")
    asset, version = _resolve(db, link, body.asset_id, body.version_id)

    if current_user:
        email, name, author_id, guest_id = current_user.email.lower(), current_user.name, current_user.id, None
    else:
        if not body.guest_email or not body.guest_name:
            raise HTTPException(400, "guest_name and guest_email are required")
        email, name = body.guest_email.strip().lower(), body.guest_name.strip()
        guest = db.query(GuestUser).filter(GuestUser.email == email).first()
        if not guest:
            guest = GuestUser(email=email, name=name)
            db.add(guest); db.flush()
        author_id, guest_id = None, guest.id

    db.execute(text("""
        INSERT INTO osc_guest_approvals (id, share_link_id, asset_id, version_id, email, name, status, note)
        VALUES (:id, :l, :a, :v, :e, :n, :s, :note)
        ON CONFLICT (version_id, email) DO UPDATE
          SET status = EXCLUDED.status, note = EXCLUDED.note, name = EXCLUDED.name, created_at = now()"""),
        {"id": str(uuid.uuid4()), "l": str(link.id), "a": str(asset.id), "v": str(version.id),
         "e": email, "n": name, "s": decision, "note": (body.note or "").strip() or None})

    label = "✅ Approved" if decision == "approved" else "🔁 Changes requested"
    note = (body.note or "").strip()
    db.add(Comment(asset_id=asset.id, version_id=version.id, author_id=author_id, guest_author_id=guest_id,
                   body=f"{label}: {note}" if note else label, visibility="public"))
    db.add(ShareLinkActivity(share_link_id=link.id,
                             action=ShareActivityAction.approved if decision == "approved" else ShareActivityAction.rejected,
                             actor_email=email, actor_name=name, asset_id=asset.id, asset_name=asset.name))
    db.commit()
    sync_status(db, asset, version.id)
    event_service.publish_sync(asset.project_id, "approval_updated",
                               {"asset_id": str(asset.id), "status": decision, "via": "share_link"})
    return {"decision": decision, "version_id": str(version.id), "asset_status": asset.status.value
            if hasattr(asset.status, "value") else str(asset.status)}


@router.get("/share/{token}/decisions")
def share_decisions(token: str, asset_id: Optional[uuid.UUID] = None, version_id: Optional[uuid.UUID] = None,
                    share_session: Optional[str] = Query(None), db: Session = Depends(get_db),
                    current_user: Optional[User] = Depends(get_optional_user)):
    link = validate_share_link_with_session(db, token, share_session=share_session, current_user=current_user)
    asset, version = _resolve(db, link, asset_id, version_id)
    rows = db.execute(text("SELECT name, status, created_at FROM osc_guest_approvals WHERE version_id = :v "
                           "ORDER BY created_at"), {"v": str(version.id)}).fetchall()
    return [{"name": r[0], "decision": r[1], "at": r[2].isoformat() if r[2] else None} for r in rows]
