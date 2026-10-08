"""OSC 0016: merge items into ONE item with the versions stacked (Sam 10/8: "The entire point of Frame is to
stack new versions on top of the old versions ... you have all the versions as separate files").

FreeFrame can't move a version between assets, and re-uploading loses the comments. This moves the rows:
each source version (with its media files, comments, guest decisions and notifications) becomes a version of
the TARGET item, and the whole stack is renumbered oldest-first (v1 = oldest upload, newest on top). Nothing
is deleted: the emptied source items move to the project's `_archive` folder, renamed "(merged into …)".
S3 keys are untouched (they are stored strings; the orphan sweep derives liveness from them), and the
source items are never soft-deleted, so the retention GC can't reach the moved files.

Guards:
  - superadmin only
  - target and sources in the same project, live, not the same item
  - REFUSES (409) if any source is served by an ENABLED share link (single-asset, multi-item, or a link
    whose folder holds it): a client link must keep showing exactly what the client got
  - dry_run=true returns the plan and changes nothing

POST /osc/admin/merge {target_asset_id, sources: [{asset_id, label?}], dry_run}
  label: optional human label for that source's versions ("v8 · ALT B Homeward"), stored in
  osc_version_labels and shown instead of the file-name label.
"""
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..database import get_db
from ..middleware.auth import get_current_user
from ..models.asset import Asset, AssetVersion
from ..models.user import User

router = APIRouter(tags=["osc_merge"])
ARCHIVE = "_archive"


class Source(BaseModel):
    asset_id: uuid.UUID
    label: Optional[str] = None


class MergeIn(BaseModel):
    target_asset_id: uuid.UUID
    sources: list[Source]
    dry_run: bool = True
    # Token prefixes of links checked by hand (e.g. an internal reviewer link) that may see the change.
    override_links: list[str] = []
    # OSC 0018 (Sam 10/8 19:05: no separate delivery items): a source served by client links may be merged
    # if those links are REPOINTED to the target and the target's top version is byte-identical to the file
    # they served (the master ends on top of the deliverable's stack).
    repoint_links: bool = False


def plan_order(rows):
    """rows: [(version_id, created_at, from_target: bool, source_rank: int, old_number)] ->
    [(version_id, new_number)], oldest upload first. Ties: target's versions first, then sources in the
    order given, then the old number. Pure, so it is tested without a database."""
    key = lambda r: (r[1] or datetime.min, 0 if r[2] else 1, r[3], r[4])
    return [(r[0], i + 1) for i, r in enumerate(sorted(rows, key=key))]


def _enabled_links_serving(db: Session, asset: Asset, override=()) -> list[str]:
    q = text("""
        SELECT DISTINCT sl.token, sl.title FROM share_links sl
        LEFT JOIN share_link_items sli ON sli.share_link_id = sl.id
        WHERE sl.is_enabled AND sl.deleted_at IS NULL
          AND (sl.asset_id = :a OR sli.asset_id = :a
               OR (:f IS NOT NULL AND (sl.folder_id = :f OR sli.folder_id = :f))
               -- a whole-project link (no asset, folder or items) serves every item in the project
               OR (sl.project_id = :p AND sl.asset_id IS NULL AND sl.folder_id IS NULL
                   AND NOT EXISTS (SELECT 1 FROM share_link_items x WHERE x.share_link_id = sl.id)))""")
    rows = db.execute(q, {"a": str(asset.id), "f": str(asset.folder_id) if asset.folder_id else None,
                          "p": str(asset.project_id)})
    return [f"{r[1]} ({r[0][:8]})" for r in rows if not any(r[0].startswith(o) for o in override if o)]


@router.post("/osc/admin/merge")
def merge(body: MergeIn, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not getattr(current_user, "is_superadmin", False):
        raise HTTPException(403, "Superadmin only")
    target = db.query(Asset).filter(Asset.id == body.target_asset_id, Asset.deleted_at.is_(None)).first()
    if not target:
        raise HTTPException(404, "Target item not found")
    if not body.sources:
        raise HTTPException(400, "No sources")
    sources, repointed = [], []
    for s in body.sources:
        a = db.query(Asset).filter(Asset.id == s.asset_id, Asset.deleted_at.is_(None)).first()
        if not a:
            raise HTTPException(404, f"Source {s.asset_id} not found")
        if a.id == target.id:
            raise HTTPException(400, "A source can't be the target")
        if a.project_id != target.project_id:
            raise HTTPException(400, f"Source {a.name!r} is in another project")
        # A FOLDER link serves whatever is in its folder and can't be repointed; merging moves the source
        # to _archive, which would empty that link (10/8: TWwa + i0CNF went blank this way). Refuse unless
        # the target already sits in the same folder (then the link keeps serving the stack).
        if a.folder_id and a.folder_id != target.folder_id:
            folder_links = db.execute(text("""
                SELECT DISTINCT sl.token, sl.title FROM share_links sl
                LEFT JOIN share_link_items sli ON sli.share_link_id = sl.id
                WHERE sl.is_enabled AND sl.deleted_at IS NULL AND (sl.folder_id = :f OR sli.folder_id = :f)"""),
                {"f": str(a.folder_id)}).fetchall()
            if folder_links:
                raise HTTPException(409, f"Source {a.name!r} is served through FOLDER link(s) "
                                         f"{[f'{t} ({k[:8]})' for k, t in folder_links]}; move the target into that "
                                         "folder first, or the link would go empty")
        served = _enabled_links_serving(db, a, body.override_links)
        if served and not body.repoint_links:
            raise HTTPException(409, f"Source {a.name!r} is served by enabled share link(s) {served}; "
                                     "a client link must keep showing what the client got")
        sources.append((a, s.label))
        if served:
            repointed.append((a, served))

    rank = {a.id: i for i, (a, _) in enumerate(sources)}
    versions = db.query(AssetVersion).filter(
        AssetVersion.asset_id.in_([target.id] + [a.id for a, _ in sources]),
        AssetVersion.deleted_at.is_(None)).all()
    rows = [(v.id, v.created_at, v.asset_id == target.id, rank.get(v.asset_id, -1), v.version_number) for v in versions]
    order = plan_order(rows)
    by_id = {v.id: v for v in versions}
    name_of = {target.id: target.name, **{a.id: a.name for a, _ in sources}}
    plan = [{"version_id": str(vid), "from": name_of[by_id[vid].asset_id], "old": by_id[vid].version_number,
             "new": n, "created_at": by_id[vid].created_at.isoformat() if by_id[vid].created_at else None}
            for vid, n in order]
    # Repointed links must keep serving the identical file: the stack's new top must be byte-identical to
    # the latest version each repointed source served (same size + same original file name).
    if repointed and order:
        def _file(vid):
            return db.execute(text("SELECT file_size_bytes, original_filename FROM media_files WHERE version_id = :v "
                                   "ORDER BY created_at LIMIT 1"), {"v": str(vid)}).first()
        top_file = _file(order[-1][0])
        for a, served in repointed:
            mine = [v for v in versions if v.asset_id == a.id]
            src_top = max(mine, key=lambda v: v.version_number, default=None)
            if src_top is None or top_file is None or tuple(_file(src_top.id) or ()) != tuple(top_file):
                raise HTTPException(409, f"Links {served} on {a.name!r} would serve a different file after the "
                                         "merge (the new top version isn't the file they served)")
        repoint_ok = {t for _, served in repointed for t in served}
    else:
        repoint_ok = set()
    # A target that a client link serves must keep the same version on top (links without "show all
    # versions" serve the latest), so a merge may only add OLDER versions underneath it.
    target_links = [t for t in _enabled_links_serving(db, target, body.override_links) if t not in repoint_ok]
    if target_links and order:
        cur_top = max((v for v in versions if v.asset_id == target.id), key=lambda v: v.version_number, default=None)
        if cur_top is None or order[-1][0] != cur_top.id:
            raise HTTPException(409, f"Target is served by enabled share link(s) {target_links} and this merge "
                                     "would change the version on top")
    if body.dry_run:
        return {"dry_run": True, "target": target.name, "stack": plan}

    orig_owner = {v.id: v.asset_id for v in versions}  # captured BEFORE anything moves
    # Two-step renumber (uq_asset_versions_asset_version): park every number negative, then assign.
    for v in versions:
        v.version_number = -abs(v.version_number) - 100000
    db.flush()
    for vid, n in order:
        by_id[vid].asset_id = target.id
        by_id[vid].version_number = n
    db.flush()
    src_ids = [str(a.id) for a, _ in sources]
    params = {"t": str(target.id), "s": src_ids}
    for table in ("comments", "osc_guest_approvals", "notifications"):
        db.execute(text(f"UPDATE {table} SET asset_id = :t WHERE asset_id = ANY(CAST(:s AS uuid[]))"), params)
    db.execute(text("UPDATE activity_logs SET asset_id = :t WHERE asset_id = ANY(CAST(:s AS uuid[]))"), params)
    if repointed:  # OSC 0018: the client links now serve the target (checked above: same file on top)
        db.execute(text("UPDATE share_links SET asset_id = :t WHERE asset_id = ANY(CAST(:s AS uuid[]))"), params)
        db.execute(text("""DELETE FROM share_link_items x WHERE x.asset_id = ANY(CAST(:s AS uuid[]))
                           AND EXISTS (SELECT 1 FROM share_link_items y WHERE y.share_link_id = x.share_link_id
                                       AND y.asset_id = :t)"""), params)
        db.execute(text("UPDATE share_link_items SET asset_id = :t WHERE asset_id = ANY(CAST(:s AS uuid[]))"), params)
        db.execute(text("UPDATE asset_shares SET asset_id = :t WHERE asset_id = ANY(CAST(:s AS uuid[]))"), params)
    for a, label in sources:
        if not label:
            continue
        for vid, owner in orig_owner.items():
            if owner == a.id:
                db.execute(text("""INSERT INTO osc_version_labels (version_id, label) VALUES (:v, :l)
                                   ON CONFLICT (version_id) DO UPDATE SET label = EXCLUDED.label"""),
                           {"v": str(vid), "l": label[:120]})
    # Archive the emptied sources (never deleted: the GC must not reach the moved files).
    folder_id = db.execute(text("SELECT id FROM folders WHERE project_id = :p AND name = :n AND deleted_at IS NULL "
                                "ORDER BY created_at LIMIT 1"), {"p": str(target.project_id), "n": ARCHIVE}).scalar()
    if not folder_id:
        folder_id = uuid.uuid4()
        db.execute(text("INSERT INTO folders (id, project_id, name, created_by, created_at, updated_at) "
                        "VALUES (:i, :p, :n, :u, now(), now())"),
                   {"i": str(folder_id), "p": str(target.project_id), "n": ARCHIVE, "u": str(current_user.id)})
    for a, _ in sources:
        a.folder_id = folder_id
        if "(merged into" not in a.name:
            a.name = f"{a.name} (merged into {target.name})"[:255]
    db.commit()
    return {"dry_run": False, "target": target.name, "stack": plan}
