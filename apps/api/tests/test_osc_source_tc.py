"""OSC 0013: the player shows the clip's real source timecode (frame 0 = the file's embedded start
TC, e.g. 00:59:55:00 for a render with the 5 s slate pre-roll), not 00:00:00:00. Mock-based: no
Postgres in the build gate."""
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.api.services import osc_timecode
from apps.api.services.osc_timecode import nominal_fps, source_tc_for_version, tc_to_frames

R = "apps.api.routers.osc_source_tc"


# ── pure TC math ────────────────────────────────────────────────────────────

def test_non_drop_frame_bases():
    assert tc_to_frames("00:59:55:00", 24) == 86280
    assert tc_to_frames("00:59:55:00", 23.976) == 86280
    assert tc_to_frames("01:00:00:00", 25) == 90000
    assert tc_to_frames("01:00:00:00", 30) == 108000
    assert tc_to_frames("00:00:01:05", 24) == 29


def test_drop_frame_2997_and_5994():
    assert tc_to_frames("01:00:00;00", 29.97) == 107892
    assert tc_to_frames("00:01:00;02", 29.97) == 1800       # first label after a dropped pair
    assert tc_to_frames("00:10:00;00", 29.97) == 17982      # the tenth minute drops nothing
    assert tc_to_frames("01:00:00;00", 59.94) == 215784


def test_semicolon_on_a_non_drop_rate_counts_non_drop():
    assert tc_to_frames("01:00:00;00", 25) == 90000


def test_bad_input_raises():
    with pytest.raises(ValueError):
        tc_to_frames("1:00:00:00", 24)
    with pytest.raises(ValueError):
        tc_to_frames("01:00:00:00", None)
    with pytest.raises(ValueError):
        tc_to_frames("01:00:00:00", 0)


def test_nominal_fps():
    assert [nominal_fps(f) for f in (23.976, 24, 25, 29.97, 59.94)] == [24, 24, 25, 30, 60]
    assert nominal_fps(None) is None and nominal_fps("x") is None


# ── the cached service ──────────────────────────────────────────────────────

def _db(cached_row):
    db = MagicMock()
    db.execute.return_value.fetchone.return_value = cached_row
    db.query.return_value = db
    db.filter.return_value = db
    return db


def test_cache_hit_never_probes():
    db = _db(("00:59:55:00", 23.976))
    with patch.object(osc_timecode, "probe_start_tc") as p:
        out = source_tc_for_version(db, SimpleNamespace(id=uuid.uuid4()))
    p.assert_not_called()
    assert out == {"start_tc": "00:59:55:00", "fps": 23.976, "start_frames": 86280}


def test_cache_miss_probes_once_and_stores_the_row():
    db = _db(None)
    db.first.return_value = SimpleNamespace(fps=24.0, s3_key_raw="raw/k.mov")
    with patch.object(osc_timecode, "probe_start_tc", return_value="00:59:55:00") as p:
        out = source_tc_for_version(db, SimpleNamespace(id=uuid.uuid4()))
    p.assert_called_once_with("raw/k.mov")
    assert out == {"start_tc": "00:59:55:00", "fps": 24.0, "start_frames": 86280}
    insert = db.execute.call_args_list[-1]
    assert "INSERT INTO osc_version_tc" in str(insert.args[0])
    assert insert.args[1]["tc"] == "00:59:55:00" and insert.args[1]["fps"] == 24.0
    db.commit.assert_called_once()


def test_no_timecode_tag_is_cached_as_null_and_reads_as_unknown():
    db = _db(None)
    db.first.return_value = SimpleNamespace(fps=25.0, s3_key_raw="raw/k.mp4")
    with patch.object(osc_timecode, "probe_start_tc", return_value=None):
        out = source_tc_for_version(db, SimpleNamespace(id=uuid.uuid4()))
    assert out["start_frames"] is None and out["start_tc"] is None
    assert db.execute.call_args_list[-1].args[1]["tc"] is None   # stored, so not re-probed


def test_cached_null_row_is_not_reprobed():
    db = _db((None, 25.0))
    with patch.object(osc_timecode, "probe_start_tc") as p:
        out = source_tc_for_version(db, SimpleNamespace(id=uuid.uuid4()))
    p.assert_not_called()
    assert out == {"start_tc": None, "fps": 25.0, "start_frames": None}


def test_a_failed_cache_write_still_answers():
    db = _db(None)
    db.first.return_value = SimpleNamespace(fps=24.0, s3_key_raw="raw/k.mov")
    db.commit.side_effect = RuntimeError("db down")
    with patch.object(osc_timecode, "probe_start_tc", return_value="01:00:00:00"):
        out = source_tc_for_version(db, SimpleNamespace(id=uuid.uuid4()))
    assert out["start_frames"] == 86400
    db.rollback.assert_called()


# ── the routes ──────────────────────────────────────────────────────────────

def test_signed_in_route_checks_access_and_returns_the_shape(client, mock_db, auth_headers):
    asset = SimpleNamespace(id=uuid.uuid4(), deleted_at=None)
    version = SimpleNamespace(id=uuid.uuid4())
    mock_db.first.side_effect = [asset, version]
    want = {"start_tc": "00:59:55:00", "fps": 24.0, "start_frames": 86280}
    with patch(f"{R}.require_asset_access") as acc, patch(f"{R}.source_tc_for_version", return_value=want):
        r = client.get(f"/assets/{asset.id}/versions/{version.id}/source-tc", headers=auth_headers)
    assert r.status_code == 200 and r.json() == want
    acc.assert_called_once()


def test_share_route_validates_the_asset_against_the_link(client, mock_db):
    link = SimpleNamespace(id=uuid.uuid4(), asset_id=None, show_versions=False)
    asset = SimpleNamespace(id=uuid.uuid4(), deleted_at=None)
    latest = SimpleNamespace(id=uuid.uuid4())
    mock_db.first.side_effect = [asset, latest]
    mock_db.order_by.return_value = mock_db
    with patch(f"{R}.validate_share_link_with_session", return_value=link), \
         patch(f"{R}.validate_asset_in_share") as v, \
         patch(f"{R}.source_tc_for_version", return_value={"start_tc": None, "fps": None, "start_frames": None}) as s:
        r = client.get(f"/share/tok/source-tc?asset_id={asset.id}&version_id={uuid.uuid4()}")
    assert r.status_code == 200
    v.assert_called_once()
    # show_versions is off: the requested version is ignored, the latest ready one is used
    assert s.call_args.args[1] is latest


def test_share_route_needs_an_asset_for_folder_shares(client):
    link = SimpleNamespace(id=uuid.uuid4(), asset_id=None, show_versions=True)
    with patch(f"{R}.validate_share_link_with_session", return_value=link):
        r = client.get("/share/tok/source-tc")
    assert r.status_code == 400
