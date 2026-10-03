"""OSC posters (Sam 10/2/26 23:55–23:58): the grid thumbnail is a RANDOM good frame from the
program, never the 5-second slate every OSC render opens with.

  * window: after the slate (first 5 s skipped) and away from head/tail: 15%–85% of the duration
  * a pick is rejected and re-rolled (up to 5 tries) if it is near-black, near-white, a flat/fading
    frame (low contrast), or soft (low edge energy). If every try fails the best-scoring one wins.
  * checks run on a tiny 64x36 grayscale grab (no numpy, no full decode) — milliseconds each.

Used by the transcoder (default poster for every new version) and by the API's "set poster"
endpoint (hotkey T = a chosen time; Shuffle = a fresh random pick).
"""
from __future__ import annotations

import random
import subprocess
from typing import Optional

SLATE_SECONDS = 5.0
W, H = 64, 36


def _grab_gray(input_url: str, t: float) -> Optional[bytes]:
    cmd = ["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", input_url, "-frames:v", "1",
           "-vf", f"scale={W}:{H},format=gray", "-f", "rawvideo", "-"]
    try:
        out = subprocess.run(cmd, capture_output=True, timeout=60).stdout
    except Exception:
        return None
    return out if len(out) >= W * H else None


def score_frame(buf: bytes) -> tuple[bool, float, dict]:
    """(acceptable, score, metrics) for a W*H 8-bit grayscale frame."""
    px = buf[: W * H]
    n = len(px)
    mean = sum(px) / n
    var = sum((p - mean) ** 2 for p in px) / n
    std = var ** 0.5
    edge = 0
    for y in range(H):
        row = y * W
        for x in range(W - 1):
            edge += abs(px[row + x + 1] - px[row + x])
    for y in range(H - 1):
        row, nxt = y * W, (y + 1) * W
        for x in range(W):
            edge += abs(px[nxt + x] - px[row + x])
    edge /= (W - 1) * H + W * (H - 1)
    m = {"mean": round(mean, 1), "std": round(std, 1), "edge": round(edge, 2)}
    ok = 24 <= mean <= 232 and std >= 18 and edge >= 4.0
    # prefer mid exposure, contrast and detail
    s = std + 4 * edge - abs(mean - 120) * 0.3
    return ok, s, m


def window(duration: Optional[float]) -> Optional[tuple[float, float]]:
    if not duration or duration <= 1:
        return None
    lo = max(SLATE_SECONDS, 0.15 * duration) if duration > SLATE_SECONDS + 2 else 0.15 * duration
    hi = 0.85 * duration
    if hi <= lo:
        lo, hi = 0.15 * duration, 0.85 * duration
    return lo, hi


def pick_poster_time(input_url: str, duration: Optional[float], tries: int = 5,
                     rng: Optional[random.Random] = None) -> Optional[float]:
    w = window(duration)
    if not w:
        return None
    rng = rng or random.Random()
    best_t, best_s = None, float("-inf")
    for _ in range(tries):
        t = rng.uniform(*w)
        buf = _grab_gray(input_url, t)
        if buf is None:
            continue
        ok, s, _m = score_frame(buf)
        if ok:
            return t
        if s > best_s:
            best_t, best_s = t, s
    return best_t if best_t is not None else rng.uniform(*w)


def extract_poster(input_url: str, t: float, out_path: str, vf: str = "format=yuvj420p") -> bool:
    cmd = ["ffmpeg", "-y", "-v", "error", "-ss", f"{max(0.0, t):.3f}", "-i", input_url,
           "-frames:v", "1", "-vf", vf, "-q:v", "2", out_path]
    try:
        return subprocess.run(cmd, capture_output=True, timeout=120).returncode == 0
    except Exception:
        return False
