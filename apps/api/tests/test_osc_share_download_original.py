"""OSC 0014: a share-link download hands over the uploaded master (delivery), not the web MP4.

Upstream serves the MP4 remuxed from the top HLS rung on every download, including a share link's.
For OSC a share link is how a client takes delivery of the approved, slateless master, so it must
be the uploaded file. OSC_SHARE_DOWNLOAD=mp4 restores upstream's choice. (Upstream's own
test_a_share_link_download_serves_the_mp4_rung_too fails on this fork by design.)
"""
import uuid
from unittest.mock import MagicMock, patch

from apps.api.models.asset import AssetType


def _call(client, monkeypatch, mode=None, allow_download=True):
    if mode is None:
        monkeypatch.delenv("OSC_SHARE_DOWNLOAD", raising=False)
    else:
        monkeypatch.setenv("OSC_SHARE_DOWNLOAD", mode)
    asset_id = uuid.uuid4()
    link = MagicMock(id=uuid.uuid4(), asset_id=asset_id, allow_download=allow_download,
                     permission="view", show_versions=False)
    asset = MagicMock(id=asset_id, asset_type=AssetType.video, project_id=uuid.uuid4())
    asset.name = "Spot 1 — Final"
    mf = MagicMock(version_id=uuid.uuid4(), s3_key_processed="processed/p/a/v",
                   s3_key_raw="raw/p/a/v/master.mov", s3_key_download="processed/p/a/v/download.mp4",
                   s3_key_thumbnail=None, original_filename="01_SPOT_SP_v3_master.mov", duration_seconds=30.0)
    with patch("apps.api.routers.share.validate_share_link_with_session", return_value=link), \
         patch("apps.api.routers.share.validate_asset_in_share", return_value=None), \
         patch("apps.api.routers.share._get_asset", return_value=asset), \
         patch("apps.api.routers.share._get_latest_media_file", return_value=mf), \
         patch("apps.api.routers.share._log_share_activity") as log, \
         patch("apps.api.routers.share.generate_presigned_get_url", return_value="https://s3/x?sig") as presign:
        r = client.get(f"/share/tok/stream/{asset_id}?download=true")
    return r, presign, log


def test_a_share_download_serves_the_uploaded_master(client, monkeypatch):
    r, presign, log = _call(client, monkeypatch)
    assert r.status_code == 200, r.text
    assert presign.call_args_list[0][0][0] == "raw/p/a/v/master.mov"
    assert presign.call_args_list[0].kwargs["download_filename"] == "Spot 1 — Final.mov"


def test_the_download_is_logged_as_a_download(client, monkeypatch):
    from apps.api.models.share import ShareActivityAction
    _, _, log = _call(client, monkeypatch)
    assert log.call_args[0][2] == ShareActivityAction.downloaded


def test_mp4_mode_restores_upstream(client, monkeypatch):
    _, presign, _ = _call(client, monkeypatch, mode="mp4")
    assert presign.call_args_list[0][0][0] == "processed/p/a/v/download.mp4"


def test_a_link_without_downloads_still_refuses(client, monkeypatch):
    r, presign, _ = _call(client, monkeypatch, allow_download=False)
    assert r.status_code == 403
    presign.assert_not_called()
