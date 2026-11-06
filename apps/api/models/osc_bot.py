"""OSC 0028: hashed bot credentials and header-free request audit."""
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import String, DateTime, ForeignKey, JSON, Integer, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from ..database import Base

class BotToken(Base):
    __tablename__ = "bot_tokens"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    scopes: Mapped[list] = mapped_column(JSON)
    project_ids: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

class BotAudit(Base):
    __tablename__ = "bot_request_audit"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    token_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("bot_tokens.id"), nullable=True)
    operation: Mapped[str] = mapped_column(String(80))
    status: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
