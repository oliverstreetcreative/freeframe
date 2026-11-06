"""Shared GUI/REST facade and stateless Streamable HTTP MCP (JSON response mode)."""
import json
import uuid
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse
from fastapi import APIRouter, Depends, HTTPException, Request, Response, BackgroundTasks
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from fastapi.security import HTTPBearer
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session
from ..config import settings
from ..database import get_db
from ..middleware.auth import get_current_user
from ..models.osc_bot import BotRemoval
from ..models.asset import Asset
from ..models.folder import Folder
from ..models.activity import ActivityLog
from ..services.osc_bot_auth import authenticate, audit, digest, as_utc
from ..services.osc_bot_operations import TOOLS, dispatch, row, check_links
from .osc_bot_admin import superadmin
from . import assets, folders
import secrets
import hmac

router = APIRouter(tags=["osc_bot_actions"])
bearer = HTTPBearer(auto_error=False)

def action_identity(credentials=Depends(bearer), db: Session=Depends(get_db)):
    if credentials is None: raise HTTPException(401, "Credential required")
    if credentials.credentials.startswith("ffb_"):
        ctx = authenticate(db, credentials.credentials)
        return ctx.actor, ctx
    user = get_current_user(credentials, db)
    return superadmin(user), None

@router.get("/osc/actions/catalog")
def catalog(admin=Depends(superadmin)):
    return [{"name": n, "scope": s, "gui": g, "inputSchema": schema.model_json_schema()} for n,(s,schema,g) in TOOLS.items()]

def run(db, actor, ctx, name, args, tasks):
    status = 200
    try:
        return dispatch(db, actor, ctx, name, args, tasks)
    except ValidationError:
        status = 422
        raise HTTPException(422, "Invalid Review action arguments") from None
    except HTTPException as exc:
        status = exc.status_code
        raise
    except Exception:
        status = 500
        raise HTTPException(500, "Review action failed") from None
    finally:
        # Roll back an incomplete action before committing the separate audit.
        if status >= 400: db.rollback()
        if ctx:
            audit(db, ctx.token.id, name if name in TOOLS else "unknown_action", status)
        else:
            db.add(ActivityLog(user_id=actor.id, action="review_action", payload={"operation": name if name in TOOLS else "unknown_action", "status": status}))
            db.commit()

@router.post("/osc/actions/{name}")
def action(name: str, arguments: dict, tasks: BackgroundTasks, response: Response,
           identity=Depends(action_identity), db: Session=Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    actor, ctx = identity
    return run(db, actor, ctx, name, arguments, tasks)

@router.post("/mcp")
async def mcp(request: Request, tasks: BackgroundTasks, db: Session=Depends(get_db), credentials=Depends(bearer)):
    version = request.headers.get("mcp-protocol-version", "2025-03-26")
    if version not in ("2025-03-26", "2025-06-18"):
        raise HTTPException(400, "Unsupported MCP protocol version")
    origin = request.headers.get("origin")
    if origin and origin != settings.frontend_origin:
        raise HTTPException(403, "Origin refused")
    if credentials is None: raise HTTPException(401, "Bot credential required")
    ctx = await run_in_threadpool(authenticate, db, credentials.credentials)
    # Check while streaming: Content-Length is caller controlled and can be absent.
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > 65536:
            audit(db, ctx.token.id, "mcp_invalid", 413)
            raise HTTPException(413, "MCP request too large")
    headers = {"Cache-Control": "no-store"}
    try:
        body = json.loads(data)
    except (ValueError, UnicodeError):
        audit(db, ctx.token.id, "mcp_invalid", 400)
        return JSONResponse({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}, status_code=400, headers=headers)
    if not isinstance(body, dict) or body.get("jsonrpc") != "2.0" or not isinstance(body.get("method"), str):
        audit(db, ctx.token.id, "mcp_invalid", 400)
        return JSONResponse({"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid request"}}, status_code=400, headers=headers)
    ident = body.get("id")
    method = body["method"]
    if "id" not in body:
        audit(db, ctx.token.id, "mcp_notification", 202)
        return Response(status_code=202, headers=headers)
    if not isinstance(ident, (str, int)) or isinstance(ident, bool):
        raise HTTPException(400, "Invalid request id")
    params = body.get("params", {})
    if not isinstance(params, dict): raise HTTPException(400, "Invalid params")
    if method == "initialize":
        offered = params.get("protocolVersion")
        result = {"protocolVersion": offered if offered in ("2025-03-26", "2025-06-18") else "2025-06-18",
                  "capabilities": {"tools": {"listChanged": False}},
                  "serverInfo": {"name": "osc-review", "version": "0029"},
                  "instructions": "Upload multipart parts, complete, then poll get_version until ready. Never create client links or post replies."}
    elif method == "ping": result = {}
    elif method == "tools/list":
        result = {"tools": [{"name": n, "description": g, "inputSchema": schema.model_json_schema()}
                   for n,(scope,schema,g) in TOOLS.items() if scope in ctx.token.scopes]}
    elif method == "tools/call":
        name = params.get("name")
        if not isinstance(name, str): raise HTTPException(400, "Tool name required")
        try:
            value = await run_in_threadpool(run, db, ctx.actor, ctx, name, params.get("arguments", {}), tasks)
            result = {"content": [{"type": "text", "text": json.dumps(jsonable_encoder(value))}], "isError": False}
        except HTTPException as exc:
            result = {"content": [{"type": "text", "text": str(exc.detail)}], "isError": True}
        return JSONResponse({"jsonrpc": "2.0", "id": ident, "result": result}, headers=headers)
    else:
        audit(db, ctx.token.id, "mcp_unknown", 404)
        return JSONResponse({"jsonrpc": "2.0", "id": ident, "error": {"code": -32601, "message": "Method not found"}}, headers=headers)
    audit(db, ctx.token.id, "mcp_" + method.replace("/", "_"), 200)
    return JSONResponse({"jsonrpc": "2.0", "id": ident, "result": result}, headers=headers)

@router.get("/osc/admin/removals")
def pending(db: Session=Depends(get_db), admin=Depends(superadmin)):
    return [{"id": x.id, "target_type": x.target_type, "target_id": x.target_id, "reason": x.reason,
             "created_at": x.created_at} for x in db.query(BotRemoval).filter(BotRemoval.confirmed_at.is_(None)).all()]

@router.post("/osc/admin/removals/{request_id}/code")
def removal_code(request_id: uuid.UUID, response: Response, db: Session=Depends(get_db), admin=Depends(superadmin)):
    request = row(db, BotRemoval, request_id)
    if request.confirmed_at: raise HTTPException(409, "Removal already confirmed")
    value = secrets.token_urlsafe(24)
    request.code_hash = digest(value)
    request.code_expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
    db.commit()
    response.headers["Cache-Control"] = "no-store"
    return {"code": value, "expires_at": request.code_expires_at}

class Confirm(BaseModel): code: str = Field(min_length=1, max_length=128)

@router.post("/osc/admin/removals/{request_id}/confirm")
def confirm_removal(request_id: uuid.UUID, body: Confirm, db: Session=Depends(get_db), admin=Depends(superadmin)):
    request = db.query(BotRemoval).filter(BotRemoval.id == request_id).with_for_update().first()
    if request is None: raise HTTPException(404, "Removal request not found")
    if request.confirmed_at or request.code_hash is None or request.code_expires_at is None or as_utc(request.code_expires_at) <= datetime.now(timezone.utc) or not hmac.compare_digest(request.code_hash, digest(body.code)):
        raise HTTPException(409, "Removal confirmation refused")
    # Soft trash only; the existing 30-day rescue/retention policy remains in charge.
    target = row(db, Asset if request.target_type == "asset" else Folder, request.target_id)
    if request.target_type == "asset":
        check_links(db, target)
        target.deleted_at = datetime.now(timezone.utc)
    else:
        # Keep confirmation consumption and the entire soft-delete cascade atomic.
        ids = folders._get_descendant_ids(db, target.id) + [target.id]
        check_links(db, type("F", (), {"id": uuid.UUID(int=0), "folder_id": target.id, "project_id": target.project_id})())
        for asset in db.query(Asset).filter(Asset.folder_id.in_(ids), Asset.deleted_at.is_(None)).all(): check_links(db, asset)
        now = datetime.now(timezone.utc)
        db.query(Folder).filter(Folder.id.in_(ids)).update({"deleted_at": now}, synchronize_session="fetch")
        db.query(Asset).filter(Asset.folder_id.in_(ids)).update({"deleted_at": now}, synchronize_session="fetch")
    request.confirmed_at = datetime.now(timezone.utc)
    request.confirmed_by = admin.id
    request.code_hash = None
    db.add(ActivityLog(user_id=admin.id, project_id=target.project_id, action="removal_confirmed", payload={"request_id": str(request.id)}))
    db.commit()
    return {"trashed": True}
