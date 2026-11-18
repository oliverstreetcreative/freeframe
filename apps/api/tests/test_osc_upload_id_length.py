"""OSC 0034: asset_versions.upload_id fits Cloudflare R2's multipart UploadIds (~343 chars).

Upstream declared it varchar(255), so /upload/initiate failed on R2 with
StringDataRightTruncation. The model now says 1024, and osc_status_ddl widens an existing
column at API start, only ever upward.
"""
from types import SimpleNamespace

from sqlalchemy.dialects import postgresql

# The length an R2 UploadId measured on 11/17 (content is irrelevant, only the length).
R2_UPLOAD_ID = "A" * 343


class _Conn:
    """Answers the information_schema lookup with `length` and records every statement."""

    def __init__(self, length):
        self.length = length
        self.sql = []

    def execute(self, stmt):
        self.sql.append(str(stmt))
        return SimpleNamespace(scalar=lambda: self.length)


def _alters(conn):
    return [s for s in conn.sql if s.startswith("ALTER TABLE")]


def test_the_model_column_holds_an_r2_upload_id():
    from apps.api.models.asset import AssetVersion

    col = AssetVersion.__table__.c.upload_id
    assert col.type.length == 1024
    assert len(R2_UPLOAD_ID) <= col.type.length
    assert col.type.compile(dialect=postgresql.dialect()) == "VARCHAR(1024)"


def test_a_255_column_is_widened_to_1024():
    from apps.api.osc_status_ddl import widen_upload_id

    conn = _Conn(255)
    assert widen_upload_id(conn) is True
    assert _alters(conn) == ["ALTER TABLE asset_versions ALTER COLUMN upload_id TYPE varchar(1024)"]


def test_an_already_1024_column_is_left_alone():
    from apps.api.osc_status_ddl import widen_upload_id

    conn = _Conn(1024)
    assert widen_upload_id(conn) is False
    assert _alters(conn) == []


def test_it_never_narrows_a_wider_or_text_column_or_touches_a_missing_one():
    from apps.api.osc_status_ddl import widen_upload_id

    for length in (2048, None):  # wider varchar; text (or no such column) reads as NULL
        conn = _Conn(length)
        assert widen_upload_id(conn) is False
        assert _alters(conn) == []
