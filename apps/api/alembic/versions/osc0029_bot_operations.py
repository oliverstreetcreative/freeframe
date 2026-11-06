"""OSC 0029: upload integrity, reversible archive and removal requests."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
revision = "osc0029"
down_revision = "osc0028"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("bot_uploads",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("version_id", UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("filename", sa.String(500), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False, unique=True),
        sa.Column("verified_at", sa.DateTime(timezone=True)))
    op.create_table("bot_removal_requests",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("target_type", sa.String(20), nullable=False),
        sa.Column("target_id", UUID(as_uuid=True), nullable=False),
        sa.Column("requested_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reason", sa.String(1000), nullable=False),
        sa.Column("code_hash", sa.String(64)),
        sa.Column("code_expires_at", sa.DateTime(timezone=True)),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.Column("confirmed_by", UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_table("bot_archive_receipts",
        sa.Column("project_id", UUID(as_uuid=True), nullable=False),
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("target_type", sa.String(20), nullable=False),
        sa.Column("target_id", UUID(as_uuid=True), nullable=False),
        sa.Column("original_parent_id", UUID(as_uuid=True)),
        sa.Column("archive_folder_id", UUID(as_uuid=True), nullable=False),
        sa.Column("restored_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))

def downgrade():
    raise RuntimeError("Additive migration: preserve upload integrity and removal/archive history")
