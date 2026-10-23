"""OSC: set a version's poster (the grid thumbnail). Staff only.

POST /assets/{asset_id}/poster  {"time": 12.4}            -> that frame (player hotkey T)
POST /assets/{asset_id}/poster  {"random": true}          -> a fresh random good frame (Shuffle)
optional "version_id" (default: the newest ready version).

Grabs from the ORIGINAL upload over the internal S3 endpoint, writes a NEW key each time (so no
browser/CDN cache can show the old frame), points media_file.s3_key_thumbnail at it, and deletes
the previous OSC-made poster (never upstream's own thumbnail.jpg).
"""
import os
import tempfile
import time as _time
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..middleware.auth import get_current_user
from ..models.asset import Asset, AssetVersion, MediaFile, ProcessingStatus, AssetType
from ..models.user import User
from ..services.osc_visibility import is_staff
from ..services.s3_service import get_s3_client, generate_presigned_get_url, put_object, delete_object
from ..config import settings

router = APIRouter(tags=["osc_poster"])


class PosterRequest(BaseModel):
    version_id: Optional[uuid.UUID] = None
    time: Optional[float] = None
    random: bool = False


def _internal_url(key: str) -> str:
    return get_s3_client().generate_presigned_url(
        "get_object", Params={"Bucket": settings.s3_bucket, "Key": key}, ExpiresIn=900)


@router.post("/assets/{asset_id}/retranscode")
def retranscode(asset_id: uuid.UUID, version_id: Optional[uuid.UUID] = None, db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user)):
    """OSC (staff): re-run the transcode for the newest (or given) version, e.g. after an encoder
    setting changes (10/3: audio 128k -> 256k). The version shows `processing` until it finishes;
    the original upload is untouched."""
    from ..tasks.transcode_tasks import process_asset
    from ..tasks.celery_app import send_task_safe
    asset = db.query(Asset).filter(Asset.id == asset_id, Asset.deleted_at.is_(None)).first()
    if not asset:
        raise HTTPException(404, "Asset not found")
    if not is_staff(db, asset.project_id, current_user):
        raise HTTPException(403, "Only OSC staff can re-transcode")
    q = db.query(AssetVersion).filter(AssetVersion.asset_id == asset_id, AssetVersion.deleted_at.is_(None),
                                      AssetVersion.processing_status == ProcessingStatus.ready)
    version = q.filter(AssetVersion.id == version_id).first() if version_id else \
        q.order_by(AssetVersion.version_number.desc()).first()
    if not version:
        raise HTTPException(404, "No ready version")
    send_task_safe(process_asset, str(asset.id), str(version.id))
    return {"queued": True, "version_id": str(version.id)}


@router.post("/assets/{asset_id}/poster")
def set_poster(asset_id: uuid.UUID, body: PosterRequest, db: Session = Depends(get_db),
               current_user: User = Depends(get_current_user)):
    from packages.transcoder.osc_poster import pick_poster_time, extract_poster

    asset = db.query(Asset).filter(Asset.id == asset_id, Asset.deleted_at.is_(None)).first()
    if not asset:
        raise HTTPException(404, "Asset not found")
    if not is_staff(db, asset.project_id, current_user):
        raise HTTPException(403, "Only OSC staff can change a thumbnail")
    if asset.asset_type != AssetType.video:
        raise HTTPException(422, "Posters are for video assets")
    if body.time is None and not body.random:
        raise HTTPException(422, "Give a time (seconds) or random: true")

    q = db.query(AssetVersion).filter(AssetVersion.asset_id == asset_id, AssetVersion.deleted_at.is_(None),
                                      AssetVersion.processing_status == ProcessingStatus.ready)
    version = q.filter(AssetVersion.id == body.version_id).first() if body.version_id else \
        q.order_by(AssetVersion.version_number.desc()).first()
    if not version:
        raise HTTPException(404, "No ready version")
    mf = db.query(MediaFile).filter(MediaFile.version_id == version.id).first()
    if not mf or not mf.s3_key_raw:
        raise HTTPException(404, "Media file not found")

    src = _internal_url(mf.s3_key_raw)
    if body.random:
        t = pick_poster_time(src, mf.duration_seconds)
        if t is None:
            raise HTTPException(422, "Duration unknown; pick a frame with T instead")
    else:
        t = max(0.0, float(body.time))
        if mf.duration_seconds and t > mf.duration_seconds:
            raise HTTPException(422, "Time is past the end of the video")

    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, "poster.jpg")
        if not extract_poster(src, t, out) or not os.path.exists(out):
            raise HTTPException(502, "Could not grab that frame")
        data = open(out, "rb").read()

    prefix = os.path.dirname(mf.s3_key_thumbnail or "") or os.path.dirname(mf.s3_key_raw)
    key = f"{prefix}/osc_poster_{int(_time.time() * 1000)}.jpg"
    put_object(key, data, content_type="image/jpeg", cache_control="max-age=31536000, immutable")
    old = mf.s3_key_thumbnail
    mf.s3_key_thumbnail = key
    db.commit()
    if old and "/osc_poster_" in old:
        try:
            delete_object(old)
        except Exception:
            pass
    return {"version_id": str(version.id), "time": round(t, 3), "thumbnail_url": generate_presigned_get_url(key)}
