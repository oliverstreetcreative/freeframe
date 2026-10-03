"""OSC hover-scrub storyboards.

GET  /assets/{asset_id}/storyboard[?version_id=]  -> {"meta": {...}, "url": <sprite jpg>} or 404
POST /assets/{asset_id}/storyboard[?version_id=]  -> (staff) build it now (backfill / rebuild)
"""
import json
import tempfile
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..middleware.auth import get_current_user
from ..models.asset import Asset, AssetVersion, MediaFile, ProcessingStatus, AssetType
from ..models.user import User
from ..services.osc_visibility import is_staff
from ..services.permissions import require_asset_access
from ..services.s3_service import get_s3_client, generate_presigned_get_url

router = APIRouter(tags=["osc_storyboard"])


def _version(db: Session, asset_id: uuid.UUID, version_id: Optional[uuid.UUID]) -> AssetVersion:
    q = db.query(AssetVersion).filter(AssetVersion.asset_id == asset_id, AssetVersion.deleted_at.is_(None),
                                      AssetVersion.processing_status == ProcessingStatus.ready)
    v = q.filter(AssetVersion.id == version_id).first() if version_id else \
        q.order_by(AssetVersion.version_number.desc()).first()
    if not v:
        raise HTTPException(404, "No ready version")
    return v


def _asset(db: Session, asset_id: uuid.UUID) -> Asset:
    a = db.query(Asset).filter(Asset.id == asset_id, Asset.deleted_at.is_(None)).first()
    if not a:
        raise HTTPException(404, "Asset not found")
    return a


@router.get("/assets/{asset_id}/storyboard")
def get_storyboard(asset_id: uuid.UUID, version_id: Optional[uuid.UUID] = Query(None),
                   db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    from packages.transcoder.osc_sprite import keys
    asset = _asset(db, asset_id)
    require_asset_access(db, asset, current_user)
    v = _version(db, asset_id, version_id)
    k = keys(str(v.id))
    try:
        meta = json.loads(get_s3_client().get_object(Bucket=settings.s3_bucket, Key=k["json"])["Body"].read())
    except Exception:
        raise HTTPException(404, "No storyboard for this version")
    return {"version_id": str(v.id), "meta": meta, "url": generate_presigned_get_url(k["jpg"], expires_in=6 * 3600)}


@router.post("/assets/{asset_id}/storyboard")
def build_storyboard(asset_id: uuid.UUID, version_id: Optional[uuid.UUID] = Query(None),
                     db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    from packages.transcoder.osc_sprite import build_and_upload
    asset = _asset(db, asset_id)
    if not is_staff(db, asset.project_id, current_user):
        raise HTTPException(403, "Only OSC staff can build storyboards")
    if asset.asset_type != AssetType.video:
        raise HTTPException(422, "Storyboards are for video assets")
    v = _version(db, asset_id, version_id)
    mf = db.query(MediaFile).filter(MediaFile.version_id == v.id).first()
    if not mf or not mf.s3_key_raw:
        raise HTTPException(404, "Media file not found")
    s3 = get_s3_client()
    src = s3.generate_presigned_url("get_object", Params={"Bucket": settings.s3_bucket, "Key": mf.s3_key_raw},
                                    ExpiresIn=1800)
    with tempfile.TemporaryDirectory() as d:
        meta = build_and_upload(s3, settings.s3_bucket, str(v.id), src, mf.duration_seconds or 0,
                                mf.width or 0, mf.height or 0, d)
    if not meta:
        raise HTTPException(502, "Could not build the storyboard")
    return {"version_id": str(v.id), "meta": meta}
