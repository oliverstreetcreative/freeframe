"""OSC: Resolve EDL export defaults to the source's own start timecode.

OSC renders start at 00:59:55:00 (5 s slate before the 01:00:00:00 program). FreeFrame assumed
01:00:00:00 and the UI never sends ?start_tc=, so every marker landed 5 s late in Resolve.
"""
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.api.models.asset import AssetType, ProcessingStatus
from apps.api.services import osc_timecode


@pytest.fixture(autouse=True)
def _staff():
    with patch("apps.api.routers.comments.is_staff", return_value=True):
        yield


def _rows(fps=25.0):
    asset = MagicMock(id=uuid.uuid4(), asset_type=AssetType.video, deleted_at=None)
    asset.name = "Spot"
    version = MagicMock(id=uuid.uuid4(), version_number=4, processing_status=ProcessingStatus.ready, deleted_at=None)
    media = MagicMock(fps=fps, duration_seconds=58.7, s3_key_raw="raw/p/a/v/original.mov")
    c = MagicMock(id=uuid.uuid4(), parent_id=None, author_id=None, guest_author_id=None, body="Fix logo",
                  timecode_start=2.52, timecode_end=None, resolved=False,
                  created_at=datetime(2026, 10, 3, tzinfo=timezone.utc), visibility="public")
    return asset, version, media, c


@patch("apps.api.routers.comments.require_asset_access")
def test_edl_uses_the_source_start_timecode_when_none_is_given(_, client, mock_db, auth_headers):
    asset, version, media, c = _rows()
    mock_db.first.side_effect = [asset, version, media]
    mock_db.order_by.return_value = mock_db
    mock_db.all.side_effect = [[c]]
    with patch("apps.api.services.osc_timecode.probe_start_tc", return_value="00:59:55:00"):
        r = client.get(f"/assets/{asset.id}/comments/export?format=edl&version_id={version.id}", headers=auth_headers)
    assert r.status_code == 200
    # 2.52 s at 25 fps = frame 63 -> 00:59:55:00 + 63 frames = 00:59:57:13 (not 01:00:02:13)
    assert "00:59:57:13" in r.text and "01:00:02:13" not in r.text


@patch("apps.api.routers.comments.require_asset_access")
def test_an_explicit_start_tc_still_wins(_, client, mock_db, auth_headers):
    asset, version, media, c = _rows()
    mock_db.first.side_effect = [asset, version, media]
    mock_db.order_by.return_value = mock_db
    mock_db.all.side_effect = [[c]]
    with patch("apps.api.services.osc_timecode.probe_start_tc", return_value="00:59:55:00") as p:
        r = client.get(f"/assets/{asset.id}/comments/export?format=edl&version_id={version.id}&start_tc=01:00:00:00",
                       headers=auth_headers)
    assert r.status_code == 200 and "01:00:02:13" in r.text
    p.assert_not_called()


@patch("apps.api.routers.comments.require_asset_access")
def test_no_source_timecode_falls_back_to_one_hour(_, client, mock_db, auth_headers):
    asset, version, media, c = _rows()
    mock_db.first.side_effect = [asset, version, media]
    mock_db.order_by.return_value = mock_db
    mock_db.all.side_effect = [[c]]
    with patch("apps.api.services.osc_timecode.probe_start_tc", return_value=None):
        r = client.get(f"/assets/{asset.id}/comments/export?format=edl&version_id={version.id}", headers=auth_headers)
    assert r.status_code == 200 and "01:00:02:13" in r.text


def test_probe_parses_ffprobe_and_ignores_junk(monkeypatch):
    monkeypatch.setattr(osc_timecode, "get_s3_client",
                        lambda: SimpleNamespace(generate_presigned_url=lambda *a, **k: "http://x/o.mov"))
    monkeypatch.setattr(osc_timecode.subprocess, "run",
                        lambda *a, **k: SimpleNamespace(stdout="\n00:59:55:00\n00:59:55:00\n"))
    assert osc_timecode.probe_start_tc("raw/k.mov") == "00:59:55:00"
    monkeypatch.setattr(osc_timecode.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout="garbage\n"))
    assert osc_timecode.probe_start_tc("raw/k.mov") is None
    assert osc_timecode.probe_start_tc(None) is None
