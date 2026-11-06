"""OSC 0030: verify large bot uploads in the worker, outside HTTP timeouts."""
from alembic import op
import sqlalchemy as sa
revision = "osc0030"
down_revision = "osc0029"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("asset_versions", sa.Column("osc_content_sha256", sa.String(64), nullable=True))

def downgrade():
    raise RuntimeError("Additive migration: preserve upload integrity metadata")
