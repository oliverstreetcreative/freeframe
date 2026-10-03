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
