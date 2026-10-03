"""OSC hover-scrub storyboards (Sam 10/2/26 23:40: "scrubbing over videos ... makes Frame.io feel
really alive").

One JPEG sprite sheet per version + a JSON (same keys as Stacks' skim strips: count, cols, rows,
tile_w, tile_h, interval, duration) + a WebVTT thumbnails track (standard `#xywh=` cues).

  * frames: 1 per second, capped at 100 (longer videos spread 100 frames evenly)
  * tiles: 160 px wide, height from the source aspect (even), 10 per row
  * one ffmpeg pass: fps -> scale -> tile. The slate is kept on purpose (it's part of the cut).

Keys are derived from the version id (no DB column): osc/sprites/<version_id>.{jpg,json,vtt}
"""
from __future__ import annotations

import json
import math
import os
import subprocess
from typing import Optional

TILE_W = 160
COLS = 10
MAX_FRAMES = 100


def keys(version_id: str) -> dict:
    base = f"osc/sprites/{version_id}"
    return {"jpg": base + ".jpg", "json": base + ".json", "vtt": base + ".vtt"}


def build(input_url: str, duration: float, width: int, height: int, work_dir: str) -> Optional[dict]:
    """Render the sheet into work_dir. Returns {"jpg": path, "meta": dict, "vtt": text} or None."""
    if not duration or duration <= 0:
        return None
    count = max(1, min(MAX_FRAMES, int(math.ceil(duration))))
    interval = duration / count
    aspect = (height / width) if (width and height) else 9 / 16
    tile_h = max(2, int(round(TILE_W * aspect / 2)) * 2)
    cols = min(COLS, count)
    rows = int(math.ceil(count / cols))
    out = os.path.join(work_dir, "osc_sprite.jpg")
    vf = (f"fps={count}/{duration:.6f},scale={TILE_W}:{tile_h}:force_original_aspect_ratio=decrease,"
          f"pad={TILE_W}:{tile_h}:(ow-iw)/2:(oh-ih)/2,tile={cols}x{rows}")
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", input_url, "-an", "-vf", vf,
           "-frames:v", "1", "-q:v", "4", out]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=900)
    except Exception:
        return None
    if r.returncode != 0 or not os.path.exists(out):
        return None
    meta = {"count": count, "cols": cols, "rows": rows, "tile_w": TILE_W, "tile_h": tile_h,
            "interval": round(interval, 4), "duration": round(duration, 3), "v": 1}
    return {"jpg": out, "meta": meta, "vtt": vtt(meta, "osc_sprite.jpg")}


# Sharp tiers (Sam 10/3 00:40 "it's really fuzzy" on iPhone): tile width >= CSS size x DPR.
#   480 px: desktop retina grid cards (~220 CSS x 2) and the 160-CSS seek tooltip at DPR 3
#   1080 px: phone cards (~350 CSS x 3)
# Each tier is split into sheets of cols x rows tiles, kept under ~10.5 MP so iOS decodes them.
TIERS = [(480, 8, 8), (1080, 4, 4)]
TIER_Q = "4"  # ffmpeg mjpeg -q:v 4 ~ JPEG q80


def tier_keys(version_id: str, w: int, n: int) -> list[str]:
    return [f"osc/sprites/{version_id}/t{w}_{i:03d}.jpg" for i in range(1, n + 1)]


def build_tier(input_url: str, count: int, duration: float, aspect: float, w: int, cols: int, rows: int,
               work_dir: str) -> Optional[dict]:
    h = max(2, int(round(w * aspect / 2)) * 2)
    pattern = os.path.join(work_dir, f"t{w}_%03d.jpg")
    vf = (f"fps={count}/{duration:.6f},scale={w}:{h}:force_original_aspect_ratio=decrease,"
          f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,tile={cols}x{rows}")
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", input_url, "-an", "-vf", vf, "-q:v", TIER_Q, pattern]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=1800)
    except Exception:
        return None
    files = sorted(p for p in os.listdir(work_dir) if p.startswith(f"t{w}_") and p.endswith(".jpg"))
    if r.returncode != 0 or not files:
        return None
    return {"w": w, "h": h, "cols": cols, "rows": rows, "per_sheet": cols * rows,
            "sheets": len(files), "files": [os.path.join(work_dir, p) for p in files]}


def _ts(s: float) -> str:
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{int(h):02d}:{int(m):02d}:{sec:06.3f}"


def vtt(meta: dict, image_name: str) -> str:
    lines = ["WEBVTT", ""]
    for i in range(meta["count"]):
        x, y = (i % meta["cols"]) * meta["tile_w"], (i // meta["cols"]) * meta["tile_h"]
        start, end = i * meta["interval"], min(meta["duration"], (i + 1) * meta["interval"])
        lines += [f"{_ts(start)} --> {_ts(end)}", f"{image_name}#xywh={x},{y},{meta['tile_w']},{meta['tile_h']}", ""]
    return "\n".join(lines)


def meta_json(meta: dict) -> bytes:
    return json.dumps(meta).encode()


def build_and_upload(s3, bucket: str, version_id: str, input_url: str, duration: float,
                     width: int, height: int, work_dir: str) -> Optional[dict]:
    """Build the sheet and upload jpg/json/vtt with a boto3 client. Returns the meta, or None."""
    sp = build(input_url, duration, width, height, work_dir)
    if not sp:
        return None
    k = keys(version_id)
    s3.upload_file(sp["jpg"], bucket, k["jpg"],
                   ExtraArgs={"ContentType": "image/jpeg", "CacheControl": "max-age=31536000"})
    # sharp tiers (best-effort: the 160 px sheet above already works on its own)
    meta = sp["meta"]
    aspect = (height / width) if (width and height) else 9 / 16
    tiers = []
    for w, cols, rows in TIERS:
        tr = build_tier(input_url, meta["count"], duration, aspect, w, cols, rows, work_dir)
        if not tr:
            continue
        for path, key in zip(tr["files"], tier_keys(version_id, w, tr["sheets"])):
            s3.upload_file(path, bucket, key, ExtraArgs={"ContentType": "image/jpeg",
                                                         "CacheControl": "max-age=31536000"})
        tiers.append({x: tr[x] for x in ("w", "h", "cols", "rows", "per_sheet", "sheets")})
    meta = {**meta, "v": 2, "tiers": tiers}
    sp["meta"] = meta
    s3.put_object(Bucket=bucket, Key=k["json"], Body=meta_json(sp["meta"]), ContentType="application/json")
    s3.put_object(Bucket=bucket, Key=k["vtt"], Body=sp["vtt"].encode(), ContentType="text/vtt")
    return sp["meta"]
