"""OSC 0019: share KINDS — one item per deliverable, two kinds of link onto it.

Sam, 10/8: "I'm trying to avoid having separate assets for review and delivery. The final delivery
file/version won't have a slate. That's the giveaway." Review rounds are versions that carry the 5 s
house slate (start TC 00:59:55:00); the clean delivery master is uploaded as the TOP version of the
same item. A share link is one of two kinds:

  review    permission comment, download off, show_versions as chosen (default on)
  delivery  permission view, download ON, show_versions OFF (serves only the latest = the master)

A link also gets an INTERNAL LABEL (what OSC staff see in the link list; never sent to guests),
separate from its public `title`. Both live in osc_share_meta (osc_status_ddl.py), so upstream's
share_links table and share router stay untouched.

  GET /osc/projects/{project_id}/share-meta
      -> {"<link id>": {"kind", "internal_label", "inferred"}} for every live link of the project.
         No row = kind inferred from the link (view + download -> delivery, else review).
  PUT /osc/share-links/{link_id}/meta  {kind?, internal_label?, force?}
      -> upserts the row; a `kind` APPLIES ITS PRESET to the link's permission / allow_download /
         show_versions. SLATE GUARD: kind=delivery while any served item's latest ready version still
         starts at the slate TC answers 409 {"detail", "slated": [item names]} unless force=true.
"""
import uuid
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import or_, text
from sqlalchemy.orm import Session

from ..database import get_db
from ..middleware.auth import get_current_user
from ..models.asset import Asset, AssetVersion, ProcessingStatus
from ..models.folder import Folder
from ..models.project import ProjectRole
from ..models.share import ShareLink, ShareLinkItem, SharePermission
from ..models.user import User
from ..services.osc_timecode import source_tc_for_version
from ..services.permissions import require_project_role

router = APIRouter(tags=["osc_share_meta"])

SLATE_TC = "00:59:55:00"  # the house slate: 5 s pre-roll before the 01:00:00:00 program
_PROJECT_SCAN_CAP = 200  # a whole-project delivery link: check at most this many items


class MetaIn(BaseModel):
    kind: Optional[Literal["review", "delivery"]] = None
    internal_label: Optional[str] = Field(default=None, max_length=255)
    force: bool = False


def _perm(p) -> str:
    return getattr(p, "value", p) or ""


def infer_kind(permission, allow_download) -> str:
    """No osc_share_meta row: a view-only link that hands over the file is a delivery."""
    return "delivery" if _perm(permission) == "view" and bool(allow_download) else "review"


def _require_editor(db: Session, project_id, user: User) -> None:
    if getattr(user, "is_superadmin", False):
        return
    require_project_role(db, project_id, user, ProjectRole.editor)


def _link_project_id(db: Session, link: ShareLink):
    if link.project_id:
        return link.project_id
    if link.asset_id:
        a = db.query(Asset).filter(Asset.id == link.asset_id).first()
        if a:
            return a.project_id
    if link.folder_id:
        f = db.query(Folder).filter(Folder.id == link.folder_id).first()
        if f:
            return f.project_id
    raise HTTPException(404, "Share link target not found")


def _meta_rows(db: Session, ids: list) -> dict:
    """{link id str: (kind, internal_label)}; empty if the table isn't there yet."""
    if not ids:
        return {}
    try:
        rows = db.execute(text("SELECT share_link_id, kind, internal_label FROM osc_share_meta "
                               "WHERE share_link_id = ANY(CAST(:ids AS uuid[]))"),
                          {"ids": [str(i) for i in ids]}).fetchall()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        return {}
    return {str(r[0]): (r[1], r[2]) for r in rows}


@router.get("/osc/projects/{project_id}/share-meta")
def project_share_meta(project_id: uuid.UUID, db: Session = Depends(get_db),
                       current_user: User = Depends(get_current_user)):
    _require_editor(db, project_id, current_user)
    links = (db.query(ShareLink)
             .outerjoin(Asset, ShareLink.asset_id == Asset.id)
             .outerjoin(Folder, ShareLink.folder_id == Folder.id)
             .filter(ShareLink.deleted_at.is_(None),
                     or_(ShareLink.project_id == project_id, Asset.project_id == project_id,
                         Folder.project_id == project_id))
             .all())
    rows = _meta_rows(db, [l.id for l in links])
    out = {}
    for l in links:
        row = rows.get(str(l.id))
        if row:
            out[str(l.id)] = {"kind": row[0], "internal_label": row[1], "inferred": False}
        else:
            out[str(l.id)] = {"kind": infer_kind(l.permission, l.allow_download), "internal_label": None,
                              "inferred": True}
    return out


# ── the slate guard ──────────────────────────────────────────────────────────

def served_assets(db: Session, link: ShareLink) -> list:
    """The items a link serves: its asset; a folder's assets; a multi-link's items (and the assets of
    any folders among them); a whole-project link's assets (capped)."""
    live = Asset.deleted_at.is_(None)
    if link.asset_id:
        return db.query(Asset).filter(Asset.id == link.asset_id, live).all()
    if link.folder_id:
        return db.query(Asset).filter(Asset.folder_id == link.folder_id, live).all()
    items = db.query(ShareLinkItem).filter(ShareLinkItem.share_link_id == link.id).all()
    if items:
        a_ids = [i.asset_id for i in items if i.asset_id]
        f_ids = [i.folder_id for i in items if i.folder_id]
        conds = []
        if a_ids:
            conds.append(Asset.id.in_(a_ids))
        if f_ids:
            conds.append(Asset.folder_id.in_(f_ids))
        return db.query(Asset).filter(or_(*conds), live).all() if conds else []
    if link.project_id:
        return db.query(Asset).filter(Asset.project_id == link.project_id, live).limit(_PROJECT_SCAN_CAP).all()
    return []


def latest_ready_version(db: Session, asset_id):
    return (db.query(AssetVersion)
            .filter(AssetVersion.asset_id == asset_id, AssetVersion.deleted_at.is_(None),
                    AssetVersion.processing_status == ProcessingStatus.ready)
            .order_by(AssetVersion.version_number.desc())
            .first())


def slated_items(db: Session, link: ShareLink) -> list:
    """Names of served items whose latest ready version still starts on the house slate."""
    names = []
    for asset in served_assets(db, link):
        v = latest_ready_version(db, asset.id)
        if v is None:
            continue
        if source_tc_for_version(db, v).get("start_tc") == SLATE_TC:
            names.append(asset.name)
    return names


@router.put("/osc/share-links/{link_id}/meta")
def put_share_meta(link_id: uuid.UUID, body: MetaIn, db: Session = Depends(get_db),
                   current_user: User = Depends(get_current_user)):
    link = db.query(ShareLink).filter(ShareLink.id == link_id, ShareLink.deleted_at.is_(None)).first()
    if not link:
        raise HTTPException(404, "Share link not found")
    _require_editor(db, _link_project_id(db, link), current_user)

    row = _meta_rows(db, [link.id]).get(str(link.id))
    current_kind = row[0] if row else infer_kind(link.permission, link.allow_download)
    current_label = row[1] if row else None

    # The guard runs BEFORE any write: source_tc_for_version may commit its own TC cache.
    if body.kind == "delivery" and not body.force:
        slated = slated_items(db, link)
        if slated:
            return JSONResponse(status_code=409, content={
                "detail": (f"The latest version of {len(slated)} item(s) still has the review slate "
                           f"(starts {SLATE_TC}). A delivery link should serve the clean master: upload it "
                           "as the top version, or use anyway."),
                "slated": slated})

    if body.kind == "delivery":
        link.permission = SharePermission.view
        link.allow_download = True
        link.show_versions = False
    elif body.kind == "review":
        link.permission = SharePermission.comment
        link.allow_download = False
        if current_kind == "delivery":
            link.show_versions = True

    kind = body.kind or current_kind
    if "internal_label" in body.model_fields_set:
        label = (body.internal_label or "").strip() or None
    else:
        label = current_label

    db.execute(text("""
        INSERT INTO osc_share_meta (share_link_id, kind, internal_label, updated_at)
        VALUES (:l, :k, :lab, now())
        ON CONFLICT (share_link_id) DO UPDATE
          SET kind = EXCLUDED.kind, internal_label = EXCLUDED.internal_label, updated_at = now()"""),
        {"l": str(link.id), "k": kind, "lab": label})
    db.commit()
    return {"kind": kind, "internal_label": label, "permission": _perm(link.permission),
            "allow_download": bool(link.allow_download), "show_versions": bool(link.show_versions)}
