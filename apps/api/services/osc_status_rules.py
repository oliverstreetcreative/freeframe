"""OSC status labels: the auto-rule, shared by staff approvals and client (share-link) decisions.

Decisions on the asset's LATEST version drive the label: any "changes requested" -> rejected
(Changes requested, red); otherwise any approval -> approved (Approved, green). Decisions on an older
version never move it (a new version already reset it to Needs review)."""
import uuid

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..models.approval import Approval, ApprovalStatus
from ..models.asset import Asset, AssetStatus, AssetVersion


def latest_version_id(db: Session, asset_id) -> "uuid.UUID | None":
    v = (db.query(AssetVersion)
         .filter(AssetVersion.asset_id == asset_id, AssetVersion.deleted_at.is_(None))
         .order_by(AssetVersion.version_number.desc()).first())
    return v.id if v else None


def guest_decisions(db: Session, version_id) -> set:
    try:
        rows = db.execute(text("SELECT status FROM osc_guest_approvals WHERE version_id = :v"),
                          {"v": str(version_id)}).fetchall()
    except Exception:  # table not created yet (DDL runs at API start)
        db.rollback()
        return set()
    return {r[0] for r in rows}


def sync_status(db: Session, asset: Asset, version_id) -> None:
    if latest_version_id(db, asset.id) != version_id:
        return
    staff = {a.status for a in db.query(Approval).filter(Approval.version_id == version_id,
                                                         Approval.deleted_at.is_(None))}
    guests = guest_decisions(db, version_id)
    if ApprovalStatus.rejected in staff or "rejected" in guests:
        asset.status = AssetStatus.rejected
    elif ApprovalStatus.approved in staff or "approved" in guests:
        asset.status = AssetStatus.approved
    else:
        return
    db.commit()
