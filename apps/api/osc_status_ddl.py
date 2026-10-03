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
    print("osc_status_ddl: assetstatus has client_review")


if __name__ == "__main__":
    main()
