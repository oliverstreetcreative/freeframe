"""Human-session-only credential management. Bot tokens never enter get_current_user."""
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field, AwareDatetime
from sqlalchemy.orm import Session
from ..database import get_db
from ..middleware.auth import get_current_user
from ..models.user import User
from ..models.osc_bot import BotToken
from ..services.osc_bot_auth import issue, audit

router = APIRouter(prefix="/osc/admin/bot-tokens", tags=["osc_bot_admin"])

def superadmin(user: User = Depends(get_current_user)):
    if not user.is_superadmin:
        raise HTTPException(403, "Superadmin only")
    return user

class TokenCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    scopes: list[str]
    project_ids: list[uuid.UUID] | None = None
    expires_at: AwareDatetime | None = None

def public(row):
    return {k: getattr(row, k) for k in ("id", "name", "scopes", "project_ids", "created_by", "created_at",
                                         "expires_at", "last_used_at", "revoked_at")}

@router.get("")
def list_tokens(response: Response, db: Session = Depends(get_db), admin: User = Depends(superadmin)):
    response.headers["Cache-Control"] = "no-store"
    return [public(row) for row in db.query(BotToken).order_by(BotToken.created_at.desc()).all()]

@router.post("", status_code=201)
def create_token(body: TokenCreate, response: Response, db: Session = Depends(get_db), admin: User = Depends(superadmin)):
    response.headers["Cache-Control"] = "no-store"
    row, value = issue(db, admin, body.name, body.scopes,
                       None if body.project_ids is None else [str(x) for x in body.project_ids], body.expires_at)
    return {**public(row), "token": value}

@router.post("/{token_id}/revoke")
def revoke_token(token_id: uuid.UUID, db: Session = Depends(get_db), admin: User = Depends(superadmin)):
    row = db.query(BotToken).filter(BotToken.id == token_id).first()
    if row is None:
        raise HTTPException(404, "Bot token not found")
    row.revoked_at = row.revoked_at or datetime.now(timezone.utc)
    db.commit()
    audit(db, row.id, "token_revoked", 200)
    return public(row)
