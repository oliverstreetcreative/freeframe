"""OSC 0028: additive bot authentication and audit tables."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision = "osc0028"
down_revision = "e3f5a7c9d1b2"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("bot_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("project_ids", sa.JSON(), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)))
    op.create_index("ix_bot_tokens_token_hash", "bot_tokens", ["token_hash"], unique=True)
    op.create_table("bot_request_audit",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("token_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("bot_tokens.id")),
        sa.Column("operation", sa.String(80), nullable=False),
        sa.Column("status", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))

def downgrade():
    raise RuntimeError("Additive migration: retain bot credentials and audit history")
