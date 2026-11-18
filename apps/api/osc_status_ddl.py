"""OSC status labels: add the 'client_review' value to the assetstatus Postgres enum.

Idempotent (ADD VALUE IF NOT EXISTS) and kept OUT of alembic on purpose: an extra revision in
our overlay would fork upstream's migration chain into two heads and break `alembic upgrade head`
on the next upstream release. Runs once at API start, after alembic. ALTER TYPE ... ADD VALUE
cannot run inside a transaction block on older Postgres, so it uses autocommit.
"""
from sqlalchemy import create_engine, text

from apps.api.config import settings
from apps.api.database import pin_psycopg2_driver


def main() -> None:
    # Same driver pin as apps/api/database.py (upstream #544): SQLAlchemy 2.1 reads a bare
    # postgresql:// URL (Railway's DATABASE_URL) as psycopg v3, which the image doesn't ship. Without
    # it this script dies at API start and the `&&` chain never reaches gunicorn.
    engine = create_engine(pin_psycopg2_driver(settings.database_url), isolation_level="AUTOCOMMIT")
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
        # OSC 0016: a human label for a version that came from a merged item ("v8 · ALT B Homeward"),
        # shown instead of the file-name label. Set only by the superadmin merge.
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS osc_version_labels (
                version_id uuid PRIMARY KEY REFERENCES asset_versions(id) ON DELETE CASCADE,
                label varchar(120) NOT NULL,
                created_at timestamptz NOT NULL DEFAULT now()
            )"""))
        # OSC 0019: a share link's KIND (review = comment, no download; delivery = view, download,
        # latest version only) and its INTERNAL LABEL (staff-only; the public title stays on
        # share_links.title). No row = kind inferred from the link's settings.
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS osc_share_meta (
                share_link_id uuid PRIMARY KEY REFERENCES share_links(id) ON DELETE CASCADE,
                kind varchar(16) NOT NULL CHECK (kind IN ('review', 'delivery')),
                internal_label varchar(255),
                updated_at timestamptz NOT NULL DEFAULT now()
            )"""))
        widened = widen_upload_id(conn)
    print("osc_status_ddl: assetstatus has client_review; osc_guest_approvals, osc_version_tc, "
          "osc_version_labels, osc_share_meta ready")
    print("osc_status_ddl: asset_versions.upload_id "
          + (f"widened to varchar({UPLOAD_ID_LENGTH})" if widened else "unchanged (already wide enough)"))


# OSC 0034: asset_versions.upload_id holds the S3 multipart UploadId. Upstream's migration
# b2c4d6e8f0a1 made it varchar(255), but Cloudflare R2's UploadIds are ~343 characters, so
# /upload/initiate failed with StringDataRightTruncation. The model says 1024; this brings an
# existing database (or a fresh one alembic just built at 255) up to it. It only ever WIDENS:
# nothing happens when the column is already >= 1024 (the live database was widened by hand
# 11/18) or unbounded (if upstream later makes it text). Widening a varchar is metadata-only in
# Postgres (no table rewrite); skipping it when unneeded also skips the ALTER's lock at every start.
UPLOAD_ID_LENGTH = 1024


def widen_upload_id(conn) -> bool:
    """Widen asset_versions.upload_id to varchar(UPLOAD_ID_LENGTH) if it's narrower. True if it did."""
    current = conn.execute(text(
        "SELECT character_maximum_length FROM information_schema.columns "
        "WHERE table_schema = current_schema() AND table_name = 'asset_versions' "
        "AND column_name = 'upload_id'"
    )).scalar()
    if current is None or current >= UPLOAD_ID_LENGTH:  # no such column, text, or already wide
        return False
    conn.execute(text(f"ALTER TABLE asset_versions ALTER COLUMN upload_id TYPE varchar({UPLOAD_ID_LENGTH})"))
    return True


if __name__ == "__main__":
    main()
