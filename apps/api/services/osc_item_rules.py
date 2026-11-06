"""🤖 House rules for Review item names (REVIEW-PROCESS.md §B), shared by review_upload.py and its tests.
An item is a DELIVERABLE; a version, round, WIP, date or A/B alternate in its name is what turned every
round into a separate item on 10/8."""
import re

VERSIONY = re.compile(
    r"(?:^|[\s_\-·(])("
    r"v\d+"                       # v13
    r"|r\d+"                      # r6
    r"|wip\d*"                    # wip, wip2
    r"|round\s*\d+"               # round 3
    r"|\d{4}-\d{2}-\d{2}"         # 2026-10-08
    r"|[AB]\s+(?:cut|faithful|alt)"  # A FAITHFUL, B CUT
    r"|alt(?:[\s\-]?[a-z0-9]+)?"  # ALT, ALT-B, ALT MUSIC
    r")(?=$|[\s_\-·)])",
    re.IGNORECASE,
)


def item_name_problem(name: str):
    """None if `name` names a deliverable; else the offending token."""
    m = VERSIONY.search(name or "")
    return m.group(1) if m else None


_STOP = re.compile(r"^(\d{4}|v\d+|r\d+|wip\d*|sq|square|standin)$", re.IGNORECASE)


def alt_option(filename: str, item_name: str):
    """The OPTION part of a same-round alternate's file name, for its label (Majordomo 10/8 22:15):
    '01_DEEP-END-FILMS-B-LASTAIR_2026-10-08_OSC_v2.mp4' on item '01_DEEP-END-FILMS' -> 'B lastair'.
    = the tokens after the item's own name, up to the date / vN / SQ. None if there are none."""
    stem = (filename or "").rsplit("/", 1)[-1].rsplit(".", 1)[0]
    toks = [t for t in re.split(r"[_\-\s]+", stem) if t]
    want = [t for t in re.split(r"[_\-\s]+", (item_name or "").split("—")[0]) if t and t.isalnum()]
    i = j = 0
    if toks and want and toks[0].isdigit() and want[0].isdigit():  # a '03_' option file on a '02_' item
        i, j = 1, 1
    while i < len(toks) and j < len(want) and toks[i].lower() == want[j].lower():
        i, j = i + 1, j + 1
    opt = []
    for t in toks[i:]:
        if _STOP.match(t):
            break
        opt.append(t)
    if not opt:
        return None
    return " ".join(t.upper() if len(t) == 1 else t.lower() for t in opt)
