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
    print("osc_status_ddl: assetstatus has client_review")


if __name__ == "__main__":
    main()
