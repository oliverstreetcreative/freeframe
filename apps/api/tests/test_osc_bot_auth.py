"""Real persistence for credentials; no production network or credentials."""
import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from apps.api.models.user import User, UserStatus
from apps.api.models.osc_bot import BotToken, BotAudit
from apps.api.services.osc_bot_auth import authenticate, issue, SCOPES
from apps.api.config import settings

@pytest.fixture
def tokens(monkeypatch):
    monkeypatch.setattr(settings, 'osc_bot_access_enabled', True)
    engine = create_engine('sqlite://')
    for table in (User.__table__, BotToken.__table__, BotAudit.__table__):
        table.create(engine)
    with Session(engine) as db:
        admin = User(id=uuid.uuid4(), email='admin@example.invalid', name='Admin', status=UserStatus.active,
                     is_superadmin=True, email_verified=True)
        db.add(admin); db.commit()
        with patch('apps.api.services.osc_bot_auth.rate_limit'):
            yield db, admin
    engine.dispose()

def test_hash_only_and_distinct_non_login_actor(tokens):
    db, admin = tokens
    row, value = issue(db, admin, 'fixture', ['read'])
    assert value.startswith('ffb_') and row.token_hash == hashlib.sha256(value.encode()).hexdigest()
    assert value not in repr(row.__dict__)
    ctx = authenticate(db, value)
    assert ctx.actor.id != admin.id and ctx.actor.name == '🤖 fixture'
    assert ctx.actor.status == UserStatus.deactivated and not ctx.actor.is_superadmin
    assert ctx.token.last_used_at is not None
    assert 'token_hash' not in __import__('apps.api.routers.osc_bot_admin', fromlist=['public']).public(row)

def test_revoked_refused_on_next_request(tokens):
    db, admin = tokens
    row, value = issue(db, admin, 'fixture', ['read'])
    authenticate(db, value)
    row.revoked_at = datetime.now(timezone.utc); db.commit()
    with pytest.raises(HTTPException) as e: authenticate(db, value)
    assert e.value.status_code == 401
    assert db.query(BotAudit).order_by(BotAudit.created_at.desc()).count() == 2

@pytest.mark.parametrize('value', ['', 'wrong', 'ffb_' + 'A'*43, 'Bearer ffb_' + 'A'*43])
def test_bad_token(tokens, value):
    with pytest.raises(HTTPException) as e: authenticate(tokens[0], value)
    assert e.value.status_code == 401

def test_feature_off(tokens, monkeypatch):
    db, admin = tokens
    _, value = issue(db, admin, 'fixture', ['read'])
    monkeypatch.setattr(settings, 'osc_bot_access_enabled', False)
    with pytest.raises(HTTPException) as e: authenticate(db, value)
    assert e.value.status_code == 401


def test_expired(tokens):
    db, admin = tokens
    row, value = issue(db, admin, 'fixture', ['read'])
    row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1); db.commit()
    with pytest.raises(HTTPException) as e: authenticate(db, value)
    assert e.value.status_code == 401


def test_scopes_and_allowlist(tokens):
    db, admin = tokens
    project = str(uuid.uuid4())
    _, value = issue(db, admin, 'fixture', ['read'], [project])
    ctx = authenticate(db, value)
    ctx.require('read', project)
    for scope, pid in [('upload', project), ('read', uuid.uuid4())]:
        with pytest.raises(HTTPException) as e: ctx.require(scope, pid)
        assert e.value.status_code == 403

@pytest.mark.parametrize('scopes', [['superadmin'], ['share'], ['notes:write'], []])
def test_no_delivery_or_reply_scope(tokens, scopes):
    with pytest.raises(HTTPException): issue(*tokens, 'fixture', scopes)


def test_audit_contains_no_credential(tokens):
    db, admin = tokens
    _, value = issue(db, admin, 'fixture', list(SCOPES))
    with pytest.raises(HTTPException): authenticate(db, value + 'bad')
    assert all(value not in repr(row.__dict__) for row in db.query(BotAudit).all())


def test_rate_limit_and_outage():
    from apps.api.services.osc_bot_auth import rate_limit
    with patch('apps.api.services.osc_bot_auth.get_redis') as r:
        r.return_value.pipeline.return_value.execute.return_value = [settings.osc_bot_requests_per_minute + 1, True]
        with pytest.raises(HTTPException) as e: rate_limit(uuid.uuid4())
        assert e.value.status_code == 429
        r.side_effect = RuntimeError('unavailable')
        with pytest.raises(HTTPException) as e: rate_limit(uuid.uuid4())
        assert e.value.status_code == 503
