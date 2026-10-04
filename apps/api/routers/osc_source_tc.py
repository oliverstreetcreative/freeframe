"""OSC 0013: the clip's real source timecode, for the player's timecode display.

FreeFrame's player counts timecode from 00:00:00:00 at frame 0. OSC renders start at 00:59:55:00
(a 5 s slate pre-roll before the 01:00:00:00 program) and a slateless master carries its own start
TC, so a note "at 00:00:12:00" in the review site didn't match the same frame in Resolve. The web
player now offsets its display by the version's embedded start TC, read here (probed once, cached
in osc_version_tc). Stored comment times stay seconds-from-0; only the display changes.

  GET /assets/{asset_id}/versions/{version_id}/source-tc         (signed in; asset access)
  GET /share/{token}/source-tc?asset_id=&version_id=&share_session=   (share-link guests)
    -> {"start_tc": "00:59:55:00" | null, "fps": 23.976 | null, "start_frames": int | null}
"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..middleware.auth import get_current_user, get_optional_user
from ..models.asset import Asset, AssetVersion, ProcessingStatus
from ..models.user import User
from ..services.osc_timecode import source_tc_for_version
from ..services.permissions import require_asset_access, validate_asset_in_share, validate_share_link_with_session

router = APIRouter(tags=["osc_source_tc"])


def _asset(db: Session, asset_id) -> Asset:
    asset = db.query(Asset).filter(Asset.id == asset_id, Asset.deleted_at.is_(None)).first()
    if not asset:
        raise HTTPException(404, "Asset not found")
    return asset


@router.get("/assets/{asset_id}/versions/{version_id}/source-tc")
def get_source_tc(asset_id: uuid.UUID, version_id: uuid.UUID, db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user)):
    asset = _asset(db, asset_id)
    require_asset_access(db, asset, current_user)
    version = db.query(AssetVersion).filter(AssetVersion.id == version_id, AssetVersion.asset_id == asset.id,
                                            AssetVersion.deleted_at.is_(None)).first()
    if not version:
        raise HTTPException(404, "Version not found")
    return source_tc_for_version(db, version)


@router.get("/share/{token}/source-tc")
def get_share_source_tc(token: str, asset_id: Optional[uuid.UUID] = None, version_id: Optional[uuid.UUID] = None,
                        share_session: Optional[str] = Query(None), db: Session = Depends(get_db),
                        current_user: Optional[User] = Depends(get_optional_user)):
    link = validate_share_link_with_session(db, token, share_session=share_session, current_user=current_user)
    target = link.asset_id or asset_id
    if not target:
        raise HTTPException(400, "asset_id is required for folder/project shares")
    asset = _asset(db, target)
    validate_asset_in_share(db, link, asset)
    q = db.query(AssetVersion).filter(AssetVersion.asset_id == asset.id, AssetVersion.deleted_at.is_(None),
                                      AssetVersion.processing_status == ProcessingStatus.ready)
    version = None
    # Same rule as share.get_share_stream_url: a specific version only when the link shows versions;
    # otherwise (or when it isn't visible) the latest ready version — the one the guest is watching.
    if version_id and link.show_versions:
        version = q.filter(AssetVersion.id == version_id).first()
    if not version:
        version = q.order_by(AssetVersion.version_number.desc()).first()
    if not version:
        raise HTTPException(404, "No ready version")
    return source_tc_for_version(db, version)
