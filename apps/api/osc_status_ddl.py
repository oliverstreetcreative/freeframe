"""OSC status labels: add the 'client_review' value to the assetstatus Postgres enum.

Idempotent (ADD VALUE IF NOT EXISTS) and kept OUT of alembic on purpose: an extra revision in
our overlay would fork upstream's migration chain into two heads and break `alembic upgrade head`
on the next upstream release. Runs once at API start, after alembic. ALTER TYPE ... ADD VALUE
cannot run inside a transaction block on older Postgres, so it uses autocommit.
"""
from sqlalchemy import create_engine, text

from apps.api.config import settings


def main() -> None:
    engine = create_engine(settings.database_url, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        conn.execute(text("ALTER TYPE assetstatus ADD VALUE IF NOT EXISTS 'client_review'"))
        # OSC 0010: a client's decision from a share link (guests aren't users, so upstream's
        # approvals table, which needs user_id, can't hold it). One decision per person per version.
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS osc_guest_approvals (
                id uuid PRIMARY KEY,
                share_link_id uuid NOT NULL REFERENCES share_links(id),
                asset_id uuid NOT NULL REFERENCES assets(id),
                version_id uuid NOT NULL REFERENCES asset_versions(id),
                email varchar(255) NOT NULL,
                name varchar(255) NOT NULL,
                status varchar(16) NOT NULL CHECK (status IN ('approved', 'rejected')),
                note text,
                created_at timestamptz NOT NULL DEFAULT now(),
                UNIQUE (version_id, email)
            )"""))
        # OSC 0013: cached embedded start timecode per version (one ffprobe per version, ever).
        # start_tc NULL = probed, the file has no timecode tag (cached so it isn't re-probed).
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS osc_version_tc (
                version_id uuid PRIMARY KEY REFERENCES asset_versions(id) ON DELETE CASCADE,
                start_tc varchar(16),
                fps double precision,
                probed_at timestamptz NOT NULL DEFAULT now()
            )"""))
    print("osc_status_ddl: assetstatus has client_review; osc_guest_approvals, osc_version_tc ready")


if __name__ == "__main__":
    main()
