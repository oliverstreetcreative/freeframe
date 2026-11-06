"""OSC 0029: shared, scope-checked Review actions for the GUI and MCP.

All entry points use the same registry and functions. Bot capabilities are
request-local and never become JWT sessions or superadmin permissions.
"""
import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timezone, timedelta
from typing import Literal
from fastapi import BackgroundTasks, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text, or_
from ..config import settings
from ..models.asset import Asset, AssetVersion, MediaFile, ProcessingStatus
from ..models.folder import Folder
from ..models.project import Project
from ..models.comment import Comment
from ..models.osc_bot import BotUpload, BotRemoval, BotArchive
from ..models.activity import ActivityLog
from ..routers import assets, upload, folders, comments, projects, osc_merge
from ..schemas.upload import InitiateUploadRequest, PresignPartRequest, CompleteUploadRequest
from ..schemas.asset import AssetUpdate
from ..schemas.folder import FolderCreate, AssetMoveRequest, BulkMoveRequest
from ..schemas.project import ProjectCreate
from .osc_bot_auth import BotContext, digest
from .osc_item_rules import item_name_problem
from .osc_timecode import source_tc_for_version
from . import comment_export

class Args(BaseModel):
    model_config = ConfigDict(extra="forbid")
class Empty(Args): pass
class ProjectArg(Args): project_id: uuid.UUID
class AssetArg(Args): asset_id: uuid.UUID
class VersionArg(Args): version_id: uuid.UUID
class Find(Args):
    filename: str | None = Field(default=None, max_length=500)
    sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
class Upload(ProjectArg):
    item: str = Field(min_length=1, max_length=255)
    filename: str = Field(min_length=1, max_length=500)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    file_size_bytes: int = Field(gt=0)
    mime_type: str
    new_item: bool = False
class Presign(Args):
    s3_key: str
    upload_id: str
    part_number: int = Field(ge=1, le=10000)
class Complete(Args):
    s3_key: str
    upload_id: str
    asset_id: uuid.UUID
    version_id: uuid.UUID
    parts: list[dict] = []
class CreateProject(Args):
    stem: str = Field(min_length=1, max_length=255, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    confirmed: bool = False
class CreateFolder(ProjectArg):
    name: str = Field(min_length=1, max_length=255)
    parent_id: uuid.UUID | None = None
class Rename(AssetArg): name: str = Field(min_length=1, max_length=255)
class Move(AssetArg): folder_id: uuid.UUID | None = None
class BulkMove(ProjectArg):
    asset_ids: list[uuid.UUID] = Field(default=[], max_length=100)
    folder_ids: list[uuid.UUID] = Field(default=[], max_length=100)
    target_folder_id: uuid.UUID | None = None
class Label(VersionArg): label: str = Field(max_length=120)
class Merge(Args):
    target_asset_id: uuid.UUID
    source_asset_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)
    dry_run: bool = True
class Notes(VersionArg):
    status: Literal["open", "resolved"] | None = None
    internal: bool | None = None
class Export(VersionArg): format: Literal["edl", "fcpxml", "premiere_xml", "json"] = "json"
class Address(Args):
    comment_id: uuid.UUID
    addressed: bool = True
class Target(Args):
    target_type: Literal["asset", "folder"]
    target_id: uuid.UUID
class FolderArg(Args): folder_id: uuid.UUID
class Restore(Args): receipt_id: uuid.UUID
class Removal(Target): reason: str = Field(min_length=1, max_length=1000)

# Each entry has an actual GUI path, with additional operations in Review actions.
TOOLS = {
    "list_projects": ("read", Empty, "Projects"),
    "list_folders": ("read", ProjectArg, "Project folders"),
    "list_assets": ("read", ProjectArg, "Project items and version stacks"),
    "get_asset": ("read", AssetArg, "Item details"),
    "get_version": ("read", VersionArg, "Item versions"),
    "find_upload": ("read", Find, "Review actions: find upload"),
    "upload_version": ("upload", Upload, "Review actions: upload version"),
    "presign_part": ("upload", Presign, "Upload transfer"),
    "complete_upload": ("upload", Complete, "Upload transfer"),
    "create_project": ("organize", CreateProject, "New project"),
    "create_folder": ("organize", CreateFolder, "New folder"),
    "rename_asset": ("organize", Rename, "Rename item"),
    "move_asset": ("organize", Move, "Move item"),
    "bulk_move": ("organize", BulkMove, "Move selected items"),
    "set_version_label": ("organize", Label, "Review actions: version label"),
    "merge_into_stack": ("organize", Merge, "Review actions: merge stacks"),
    "list_notes": ("notes:read", Notes, "Player notes"),
    "export_notes": ("notes:read", Export, "Player export notes"),
    "mark_note_addressed": ("organize", Address, "Resolve note"),
    "archive_asset": ("archive", AssetArg, "Review actions: archive item"),
    "archive_folder": ("archive", FolderArg, "Review actions: archive folder"),
    "list_archives": ("archive", ProjectArg, "Review actions: archived items"),
    "restore_archive": ("archive", Restore, "Review actions: restore archive"),
    "request_removal": ("remove:request", Removal, "Review actions: request removal"),
}

def row(db, cls, ident):
    q = db.query(cls).filter(cls.id == ident)
    if hasattr(cls, "deleted_at"): q = q.filter(cls.deleted_at.is_(None))
    value = q.first()
    if value is None: raise HTTPException(404, "Review target not found")
    return value

def project_for(db, value):
    if isinstance(value, AssetVersion): return row(db, Asset, value.asset_id).project_id
    if isinstance(value, Comment): return row(db, Asset, value.asset_id).project_id
    return value.project_id

def guard(ctx, scope, project_id):
    if ctx is not None: ctx.require(scope, project_id)

def check_links(db, asset):
    if osc_merge._enabled_links_serving(db, asset):
        raise HTTPException(409, "An enabled share link serves this item; a human must review it first")

def check_folder_links(db, folder):
    check_links(db, type("FolderLinkTarget", (), {"id": uuid.UUID(int=0), "folder_id": folder.id, "project_id": folder.project_id})())

def version_data(db, v):
    data = next((x for x in assets.list_asset_versions(v.asset_id, db, _actor(db)) if x.id == v.id), None)
    if data is None: raise HTTPException(404, "Version not found")
    return data

def _actor(db):
    return db.info["osc_action_actor"]

def uploads(db, filename=None, sha256=None, ctx=None):
    if not filename and not sha256: raise HTTPException(422, "Supply filename or sha256")
    q = db.query(MediaFile, AssetVersion, Asset).join(AssetVersion, MediaFile.version_id == AssetVersion.id).join(Asset, AssetVersion.asset_id == Asset.id)
    q = q.filter(Asset.deleted_at.is_(None), AssetVersion.deleted_at.is_(None))
    if ctx and ctx.token.project_ids is not None: q = q.filter(Asset.project_id.in_([uuid.UUID(x) for x in ctx.token.project_ids]))
    if filename: q = q.filter(MediaFile.original_filename == filename)
    if sha256: q = q.join(BotUpload, BotUpload.version_id == AssetVersion.id).filter(BotUpload.sha256 == sha256)
    return [{"filename": f.original_filename, "version_id": v.id, "asset_id": a.id, "project_id": a.project_id,
             "processing_status": v.processing_status} for f, v, a in q.all()]

def verify_upload_bytes(db, version, media_file):
    # Ordinary uploads keep their existing path; bot uploads cannot process until verified.
    if db.info.get("osc_verify_upload") is not True: return
    fingerprint = db.query(BotUpload).filter(BotUpload.version_id == version.id).first()
    if fingerprint is None or fingerprint.verified_at is not None: return
    from .s3_service import get_s3_client
    body = None
    try:
        body = get_s3_client().get_object(Bucket=settings.s3_bucket, Key=media_file.s3_key_raw)["Body"]
        checksum = hashlib.sha256()
        for chunk in body.iter_chunks(chunk_size=1024 * 1024): checksum.update(chunk)
        matches = hmac.compare_digest(checksum.hexdigest(), fingerprint.sha256)
    except Exception:
        raise HTTPException(503, "Could not verify upload content; retry completion") from None
    finally:
        if body is not None: body.close()
    if not matches:
        version.processing_status = ProcessingStatus.failed
        db.commit()
        raise HTTPException(409, "Uploaded content does not match sha256")
    fingerprint.verified_at = datetime.now(timezone.utc)
    db.flush()

def upload_version(db, actor, ctx, a):
    if item_name_problem(a.item): raise HTTPException(422, "Item names cannot contain a version, date, round or alternate")
    if "/" in a.filename or "\\" in a.filename: raise HTTPException(422, "filename must be a basename")
    # Serialize dedupe and item creation across workers. No process-local lock.
    if db.bind.dialect.name == "postgresql":
        lock = int(a.sha256[:16], 16) - (1 << 63)
        db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock})
    duplicate = db.query(BotUpload).filter(BotUpload.sha256 == a.sha256).first()
    existing = uploads(db, filename=a.filename, ctx=ctx)
    if duplicate is not None or existing: raise HTTPException(409, "This file was already uploaded; use find_upload")
    matches = db.query(Asset).filter(Asset.project_id == a.project_id, Asset.name == a.item, Asset.deleted_at.is_(None)).all()
    if len(matches) > 1: raise HTTPException(409, "Ambiguous item name; organize duplicate stacks first")
    if matches and a.new_item: raise HTTPException(409, "Item already exists; add a version")
    if not matches and not a.new_item: raise HTTPException(409, "Item missing; new_item=true is required")
    check_links(db, matches[0] if matches else type("NewItem", (), {"id": uuid.UUID(int=0), "folder_id": None, "project_id": a.project_id})())
    plan = upload.initiate_upload_service(InitiateUploadRequest(project_id=a.project_id,
        asset_name=a.item, asset_id=matches[0].id if matches else None,
        original_filename=a.filename, file_size_bytes=a.file_size_bytes, mime_type=a.mime_type), db, actor, commit=False)
    db.add(BotUpload(version_id=plan.version_id, filename=a.filename, sha256=a.sha256))
    db.commit()
    return {**plan.model_dump(), "state": "uploading", "next": "presign_part", "part_count":
            (a.file_size_bytes + plan.chunk_size_bytes - 1) // plan.chunk_size_bytes}

def note_data(db, v, actor, status=None, internal=None):
    info = source_tc_for_version(db, v)
    spec = comment_export.snap_fps(info["fps"]) if info.get("fps") else None
    notes = comments.list_comments(v.asset_id, v.id, None, db, actor)
    def convert(note):
        d = note.model_dump(mode="json")
        d["author_name"] = note.author.name if note.author else note.guest_author.name if note.guest_author else "Unknown"
        for end, seconds in (("in", note.timecode_start), ("out", note.timecode_end)):
            frame = comment_export.seconds_to_frames(seconds, spec) if seconds is not None and spec else None
            d[end + "_seconds"] = seconds
            d[end + "_frame"] = frame
            d[end + "_tc"] = comment_export.frames_to_tc(info["start_frames"] + frame, spec) if frame is not None and info.get("start_frames") is not None else None
        d["replies"] = [convert(x) for x in note.replies]
        return d
    return {**info, "notes": [convert(n) for n in notes if (status is None or n.resolved == (status == "resolved")) and
                              (internal is None or (n.visibility == "internal") == internal)]}

def archive(db, actor, target_type, target):
    project_id = target.project_id
    if target_type == "asset": affected = [target]
    else:
        ids = folders._get_descendant_ids(db, target.id) + [target.id]
        affected = db.query(Asset).filter(Asset.folder_id.in_(ids), Asset.deleted_at.is_(None)).all()
        # An empty folder can still be served. Check it with the same link query.
        check_links(db, type("FolderLinkTarget", (), {"id": uuid.UUID(int=0), "folder_id": target.id, "project_id": project_id})())
    for asset in affected: check_links(db, asset)
    archive_folder = db.query(Folder).filter(Folder.project_id == project_id, Folder.parent_id.is_(None),
        Folder.name == "_archive", Folder.deleted_at.is_(None)).first()
    if archive_folder is None:
        archive_folder = Folder(project_id=project_id, name="_archive", created_by=actor.id)
        db.add(archive_folder); db.flush()
    parent_field = "folder_id" if target_type == "asset" else "parent_id"
    if target.id == archive_folder.id or getattr(target, parent_field) == archive_folder.id:
        raise HTTPException(409, "Already archived")
    receipt = BotArchive(project_id=project_id, target_type=target_type, target_id=target.id,
        original_parent_id=getattr(target, parent_field), archive_folder_id=archive_folder.id)
    setattr(target, parent_field, archive_folder.id)
    db.add(receipt)
    db.add(ActivityLog(user_id=actor.id, project_id=project_id, action="archived", payload={"target_id": str(target.id)}))
    db.commit(); db.refresh(receipt)
    return {"receipt_id": receipt.id, "target_id": target.id}

def dispatch(db, actor, ctx, name, arguments, tasks=None):
    if name not in TOOLS: raise HTTPException(404, "Unknown Review action")
    scope, schema, _ = TOOLS[name]
    a = schema.model_validate(arguments)
    if ctx: ctx.require(scope)
    db.info["osc_action_actor"] = actor
    # Scope every identifier before performing any mutation or calling an existing service.
    for field, model in (("project_id", Project), ("asset_id", Asset), ("version_id", AssetVersion),
                         ("folder_id", Folder), ("parent_id", Folder), ("target_folder_id", Folder),
                         ("target_asset_id", Asset), ("comment_id", Comment)):
        ident = getattr(a, field, None)
        if ident is not None:
            obj = row(db, model, ident)
            guard(ctx, scope, obj.id if model is Project else project_for(db, obj))
    if name == "list_projects":
        q = db.query(Project).filter(Project.deleted_at.is_(None))
        if ctx and ctx.token.project_ids is not None: q = q.filter(Project.id.in_([uuid.UUID(x) for x in ctx.token.project_ids]))
        return [{"id": x.id, "name": x.name} for x in q.all()]
    if name == "list_folders": return folders.list_folders(a.project_id, None, db, actor)
    if name == "list_assets":
        result = assets.list_assets(a.project_id, True, None, db, actor)
        return [{"asset": x, "versions": assets.list_asset_versions(x.id, db, actor)} for x in result]
    if name == "get_asset": return assets.get_asset(a.asset_id, db, actor)
    if name == "get_version":
        v = row(db, AssetVersion, a.version_id)
        return {"version": version_data(db, v), "item_url": f"{settings.frontend_url}/projects/{project_for(db, v)}/assets/{v.asset_id}",
                "ready": v.processing_status == ProcessingStatus.ready}
    if name == "find_upload": return uploads(db, a.filename, a.sha256, ctx)
    if name == "upload_version": return upload_version(db, actor, ctx, a)
    if name == "presign_part":
        f = db.query(MediaFile).filter(MediaFile.s3_key_raw == a.s3_key).first()
        if f is None: raise HTTPException(404, "Upload not found")
        v = row(db, AssetVersion, f.version_id); guard(ctx, scope, project_for(db, v))
        return upload.presign_part(PresignPartRequest(**a.model_dump()), db, actor)
    if name == "complete_upload":
        db.info["osc_verify_upload"] = True
        return upload.complete_upload(CompleteUploadRequest(**a.model_dump()), tasks or BackgroundTasks(), db, actor)
    if name == "create_project":
        if ctx and ctx.token.project_ids is not None: raise HTTPException(403, "Project-scoped tokens cannot create projects")
        if not a.confirmed: raise HTTPException(409, "Confirm the job stem before creating a project")
        result = projects.create_project(ProjectCreate(name=a.stem), db, actor)
        return {"id": result.id, "name": result.name}
    if name == "create_folder":
        if a.parent_id: check_folder_links(db, row(db, Folder, a.parent_id))
        else: check_links(db, type("NewFolder", (), {"id": uuid.UUID(int=0), "folder_id": None, "project_id": a.project_id})())
        return folders.create_folder(a.project_id, FolderCreate(name=a.name, parent_id=a.parent_id), db, actor)
    if name == "rename_asset":
        if item_name_problem(a.name): raise HTTPException(422, "Item name contains a version or alternate")
        check_links(db, row(db, Asset, a.asset_id))
        return assets.update_asset(a.asset_id, AssetUpdate(name=a.name), db, actor)
    if name == "move_asset":
        if a.folder_id: check_folder_links(db, row(db, Folder, a.folder_id))
        check_links(db, row(db, Asset, a.asset_id))
        return folders.move_asset(a.asset_id, AssetMoveRequest(folder_id=a.folder_id), db, actor)
    if name == "bulk_move":
        if a.target_folder_id: check_folder_links(db, row(db, Folder, a.target_folder_id))
        for ident in a.asset_ids:
            obj = row(db, Asset, ident); guard(ctx, scope, obj.project_id); check_links(db, obj)
        for ident in a.folder_ids:
            folder = row(db, Folder, ident)
            guard(ctx, scope, folder.project_id)
            check_folder_links(db, folder)
            ids = folders._get_descendant_ids(db, folder.id) + [folder.id]
            for asset in db.query(Asset).filter(Asset.folder_id.in_(ids), Asset.deleted_at.is_(None)).all(): check_links(db, asset)
        return folders.bulk_move(a.project_id, BulkMoveRequest(**a.model_dump(exclude={"project_id"})), db, actor)
    if name == "set_version_label":
        v = row(db, AssetVersion, a.version_id); check_links(db, row(db, Asset, v.asset_id))
        return osc_merge.set_label_service(a.version_id, osc_merge.LabelIn(label=a.label), db)
    if name == "merge_into_stack":
        for ident in a.source_asset_ids:
            guard(ctx, scope, row(db, Asset, ident).project_id)
        return osc_merge.merge_service(osc_merge.MergeIn(target_asset_id=a.target_asset_id,
            sources=[osc_merge.Source(asset_id=x) for x in a.source_asset_ids], dry_run=a.dry_run), db, actor)
    if name == "list_notes": return note_data(db, row(db, AssetVersion, a.version_id), actor, a.status, a.internal)
    if name == "export_notes":
        v = row(db, AssetVersion, a.version_id)
        if a.format == "json": return note_data(db, v, actor)
        response = comments.export_comments(v.asset_id, a.format, v.id, None, None, True, db, actor)
        return {"content": response.body.decode(), "media_type": response.media_type}
    if name == "mark_note_addressed":
        c = row(db, Comment, a.comment_id)
        if bool(c.resolved) == a.addressed: return {"comment_id": c.id, "resolved": c.resolved}
        comments.resolve_comment(c.id, db, actor)
        return {"comment_id": c.id, "resolved": c.resolved}
    if name in ("archive_asset", "archive_folder"):
        kind = "asset" if name == "archive_asset" else "folder"
        return archive(db, actor, kind, row(db, Asset if kind == "asset" else Folder,
            a.asset_id if kind == "asset" else a.folder_id))
    if name == "list_archives":
        return [{"receipt_id": x.id, "target_type": x.target_type, "target_id": x.target_id, "created_at": x.created_at}
                for x in db.query(BotArchive).filter(BotArchive.project_id == a.project_id, BotArchive.restored_at.is_(None)).all()]
    if name == "restore_archive":
        receipt = row(db, BotArchive, a.receipt_id)
        target = row(db, Asset if receipt.target_type == "asset" else Folder, receipt.target_id)
        guard(ctx, scope, target.project_id)
        field = "folder_id" if receipt.target_type == "asset" else "parent_id"
        if receipt.restored_at is not None: return {"restored": True}
        if getattr(target, field) != receipt.archive_folder_id: raise HTTPException(409, "Target moved since archive")
        if receipt.original_parent_id is not None:
            parent = row(db, Folder, receipt.original_parent_id)
            check_folder_links(db, parent)
            if receipt.target_type == "folder" and parent.id in folders._get_descendant_ids(db, target.id) + [target.id]:
                raise HTTPException(409, "Original parent is now inside the archived folder")
        check_links(db, target if receipt.target_type == "asset" else type("F", (), {"id": uuid.UUID(int=0), "folder_id": target.id, "project_id": target.project_id})())
        setattr(target, field, receipt.original_parent_id)
        receipt.restored_at = datetime.now(timezone.utc)
        db.add(ActivityLog(user_id=actor.id, project_id=target.project_id, action="archive_restored", payload={"target_id": str(target.id)}))
        db.commit()
        return {"restored": True}
    if name == "request_removal":
        target = row(db, Asset if a.target_type == "asset" else Folder, a.target_id)
        guard(ctx, scope, target.project_id)
        request = BotRemoval(target_type=a.target_type, target_id=a.target_id, requested_by=actor.id, reason=a.reason)
        db.add(request); db.commit(); db.refresh(request)
        return {"request_id": request.id, "state": "pending", "deleted": False}
    raise HTTPException(404, "Unknown Review action")
