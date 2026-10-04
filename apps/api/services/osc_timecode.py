"""OSC: a version's embedded start timecode, for NLE marker export.

FreeFrame's Resolve EDL export assumed every timeline starts at 01:00:00:00, and the web UI never
sends ?start_tc=. OSC renders start at 00:59:55:00 (a 5 s slate pre-roll before the 01:00:00:00
program), so every exported marker landed 5 s late in Resolve. The source .mov carries its start
timecode in a `timecode` tag; this reads it (header only: ffprobe never decodes) so the export can
default to it.
"""
import re
import subprocess
from typing import Optional

from ..config import settings
from .s3_service import get_s3_client

_TC = re.compile(r"^\d{2}:\d{2}:\d{2}[:;]\d{2}$")


def probe_start_tc(s3_key_raw) -> Optional[str]:
    """'HH:MM:SS:FF' (';' before FF for drop-frame) from the original upload, or None."""
    if not isinstance(s3_key_raw, str) or not s3_key_raw:
        return None
    try:
        url = get_s3_client().generate_presigned_url(
            "get_object", Params={"Bucket": settings.s3_bucket, "Key": s3_key_raw}, ExpiresIn=300)
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format_tags=timecode:stream_tags=timecode",
             "-of", "default=nw=1:nk=1", url],
            capture_output=True, text=True, timeout=20).stdout
    except Exception:
        return None
    for line in out.splitlines():
        line = line.strip()
        if _TC.match(line):
            return line
    return None


# OSC 0013: the player shows the clip's REAL source timecode (frame 0 = the file's embedded start
# TC, e.g. 00:59:55:00 for a slated render), not 00:00:00:00. One probe per version, cached in
# osc_version_tc (created in osc_status_ddl.py); a None result is cached too so a file with no
# timecode tag is never re-probed on every page load.

def nominal_fps(fps) -> Optional[int]:
    """Timecode base: 23.976 -> 24, 29.97 -> 30, 59.94 -> 60; None for missing/bad input."""
    try:
        n = int(round(float(fps)))
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def tc_to_frames(tc: str, fps: float) -> int:
    """'HH:MM:SS:FF' -> absolute frame count in the nominal base. A ';' separator (drop-frame) on a
    29.97/59.94 source uses SMPTE drop-frame math (2 / 4 frame numbers skipped each minute except
    every tenth); otherwise non-drop. Raises ValueError on a malformed string or bad fps."""
    if not isinstance(tc, str) or not _TC.match(tc):
        raise ValueError(f"not a timecode: {tc!r}")
    tb = nominal_fps(fps)
    if tb is None:
        raise ValueError(f"bad fps: {fps!r}")
    hh, mm, ss, ff = (int(p) for p in re.split(r"[:;]", tc))
    total = ((hh * 60 + mm) * 60 + ss) * tb + ff
    if ";" in tc and tb in (30, 60):
        drop = 2 if tb == 30 else 4
        total_min = hh * 60 + mm
        total -= drop * (total_min - total_min // 10)
    return total


def source_tc_for_version(db, version) -> dict:
    """{start_tc, fps, start_frames} for a version; every value None when unknown."""
    from sqlalchemy import text
    from ..models.asset import MediaFile

    empty = {"start_tc": None, "fps": None, "start_frames": None}
    if version is None:
        return empty
    vid = str(version.id)
    try:
        row = db.execute(text("SELECT start_tc, fps FROM osc_version_tc WHERE version_id = :v"),
                         {"v": vid}).fetchone()
    except Exception:
        # Table missing (DDL not run yet): fall through to a live probe; clear the failed txn.
        row = None
        try:
            db.rollback()
        except Exception:
            pass
    if row is not None:
        start_tc, fps = row[0], row[1]
    else:
        mf = db.query(MediaFile).filter(MediaFile.version_id == version.id).first()
        fps = mf.fps if mf is not None else None
        start_tc = probe_start_tc(mf.s3_key_raw if mf is not None else None)
        try:
            db.execute(text("""
                INSERT INTO osc_version_tc (version_id, start_tc, fps) VALUES (:v, :tc, :fps)
                ON CONFLICT (version_id) DO UPDATE
                  SET start_tc = EXCLUDED.start_tc, fps = EXCLUDED.fps, probed_at = now()"""),
                {"v": vid, "tc": start_tc, "fps": fps})
            db.commit()
        except Exception:
            # The cache is an optimisation; never fail the request over it.
            try:
                db.rollback()
            except Exception:
                pass
    start_frames = None
    if start_tc and fps:
        try:
            start_frames = tc_to_frames(start_tc, fps)
        except ValueError:
            start_frames = None
    return {"start_tc": start_tc if start_frames is not None else None,
            "fps": float(fps) if fps else None,
            "start_frames": start_frames}
