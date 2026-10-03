"""OSC: the start-up DDL script pins the psycopg2 driver like apps/api/database.py does.

SQLAlchemy 2.1 reads a bare postgresql:// URL (Railway's DATABASE_URL) as psycopg v3, which the image
does not ship. The script runs between `alembic upgrade head` and gunicorn in the api start command,
so if it dies the API never starts. Found while rebasing onto v1.22.1 (upstream #544).
"""
from contextlib import contextmanager
from unittest.mock import MagicMock

from apps.api import osc_status_ddl


def test_a_bare_postgres_url_gets_the_psycopg2_driver(monkeypatch):
    seen = {}

    def fake_engine(url, **kw):
        seen["url"] = url
        seen["kw"] = kw
        eng = MagicMock()

        conn = MagicMock()
        conn.execute.return_value.scalar.return_value = None  # e.g. 0034's column-width probe: nothing to do

        @contextmanager
        def connect():
            yield conn
        eng.connect = connect
        return eng

    monkeypatch.setattr(osc_status_ddl, "create_engine", fake_engine)
    monkeypatch.setattr(osc_status_ddl.settings, "database_url", "postgresql://u:p@db.railway.internal:5432/railway")
    osc_status_ddl.main()
    assert seen["url"].startswith("postgresql+psycopg2://")
    assert seen["kw"]["isolation_level"] == "AUTOCOMMIT"
