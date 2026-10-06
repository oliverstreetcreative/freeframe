"""OSC 0015: show OUR version number, not the upload count (Sam 10/5: "Review v11 = our v10 ... Sam must
never translate").

FreeFrame numbers versions by upload order. OSC numbers them by review round, and the render's file
name and slate carry that number (`..._SP_v10.mov`). The label shown in the UI is read from the
version's uploaded file name; when a file carries no vN, the upload count is shown as before.
"""
import re
from typing import Optional

# `_v10`, `-v3`, ` v2` at a word boundary; the LAST one wins (`..._v8_ALT-B` -> v8).
_V = re.compile(r"(?:^|[_\-\s.])v(\d{1,4})(?=$|[_\-\s.])", re.IGNORECASE)
_WIP = re.compile(r"(?:^|[_\-\s.])wip(\d{1,3})(?=$|[_\-\s.])", re.IGNORECASE)


def version_label(filename: Optional[str]) -> Optional[str]:
    """'v10' from 'HarmonSoS_2026-10-05_SP_v10.mp4'; 'v2 wip1' from '..._v2_wip1.mov'; None if no vN."""
    if not isinstance(filename, str) or not filename:
        return None
    stem = filename.rsplit("/", 1)[-1]
    if "." in stem:
        stem = stem.rsplit(".", 1)[0]
    found = _V.findall(stem)
    if not found:
        return None
    label = f"v{int(found[-1])}"
    wip = _WIP.findall(stem)
    return f"{label} wip{int(wip[-1])}" if wip else label
