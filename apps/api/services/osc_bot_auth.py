"""No session refresh, login, share creation or privilege inheritance for bots."""
import hashlib
import hmac
import re
import secrets
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from fastapi import HTTPException
from ..config import settings
from ..models.osc_bot import BotToken, BotAudit
from ..models.user import User, UserStatus
from .redis_service import get_redis

SCOPES = frozenset({"read", "upload", "organize", "notes:read", "archive", "remove:request"})
TOKEN_PATTERN = re.compile(r"ffb_[A-Za-z0-9_-]{43}\Z")

def as_utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()

def audit(db, token_id, operation, status):
    # No URL, headers, arguments, exception detail, filename or note text.
    db.add(BotAudit(token_id=token_id, operation=operation, status=status))
    db.commit()

def rate_limit(token_id):
    try:
        r = get_redis()
        key = f"osc:bot-rate:{token_id}:{int(time.time()) // 60}"
        pipe = r.pipeline()
        pipe.incr(key)
        pipe.expire(key, 120)
        count, _ = pipe.execute()
    except Exception:
        raise HTTPException(503, "Bot rate limiter unavailable") from None
    if count > settings.osc_bot_requests_per_minute:
        raise HTTPException(429, "Bot request limit exceeded")

@dataclass
class BotContext:
    token: BotToken
    actor: User

    def require(self, scope, project_id=None):
        if scope not in self.token.scopes:
            raise HTTPException(403, "Bot scope refused")
        if project_id is not None and self.token.project_ids is not None:
            if str(project_id) not in self.token.project_ids:
                raise HTTPException(403, "Bot project refused")

def authenticate(db, value):
    row = None
    try:
        if not settings.osc_bot_access_enabled or not TOKEN_PATTERN.fullmatch(value):
            raise HTTPException(401, "Bot credential refused")
        fingerprint = digest(value)
        row = db.query(BotToken).filter(BotToken.token_hash == fingerprint).populate_existing().first()
        if row is None or not hmac.compare_digest(row.token_hash, fingerprint):
            raise HTTPException(401, "Bot credential refused")
        if row.revoked_at is not None or (row.expires_at is not None and as_utc(row.expires_at) <= datetime.now(timezone.utc)):
            raise HTTPException(401, "Bot credential refused")
        rate_limit(row.id)
        actor = db.query(User).filter(User.id == row.actor_id, User.deleted_at.is_(None)).first()
        if actor is None or actor.is_superadmin:
            raise HTTPException(401, "Bot actor refused")
        row.last_used_at = datetime.now(timezone.utc)
        db.commit()
        context = BotContext(row, actor)
        db.info["osc_bot_context"] = context
        return context
    except HTTPException as exc:
        audit(db, row.id if row else None, "authenticate", exc.status_code)
        raise

def issue(db, admin, name, scopes, project_ids=None, expires_at=None):
    if not settings.osc_bot_access_enabled:
        raise HTTPException(409, "Bot access is disabled")
    if not name.strip() or len(name) > 120 or not scopes or not set(scopes) <= SCOPES:
        raise HTTPException(422, "Invalid bot name or scopes")
    if project_ids == []:
        raise HTTPException(422, "Choose projects or all projects")
    if expires_at is not None and expires_at <= datetime.now(timezone.utc):
        raise HTTPException(422, "Expiry must be in the future")
    # A first-class FK actor that cannot use password, magic-code, or JWT auth.
    actor_id = uuid.uuid4()
    actor = User(id=actor_id, email=f"bot-{actor_id}@bots.invalid", name=f"🤖 {name.strip()}",
                 status=UserStatus.deactivated, is_superadmin=False, email_verified=False)
    value = "ffb_" + secrets.token_urlsafe(32)
    row = BotToken(name=name.strip(), token_hash=digest(value), actor_id=actor_id,
                   scopes=sorted(set(scopes)), project_ids=project_ids, created_by=admin.id,
                   expires_at=expires_at)
    db.add(actor)
    db.flush()
    db.add(row)
    db.commit()
    db.refresh(row)
    audit(db, row.id, "token_created", 201)
    return row, value
