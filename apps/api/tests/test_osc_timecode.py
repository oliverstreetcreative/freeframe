"""OSC: probe a source's own embedded start timecode (services/osc_timecode.py).

OSC renders start at 00:59:55:00 (5 s slate before the 01:00:00:00 program). The EDL export half of
OSC 0009 is upstream since v1.16.0 (#441, our issue #440) and is covered by upstream's
test_comments_export_endpoint.py; this service stays because OSC 0013 (player source TC) uses it.
"""
from types import SimpleNamespace

from apps.api.services import osc_timecode


def test_probe_parses_ffprobe_and_ignores_junk(monkeypatch):
    monkeypatch.setattr(osc_timecode, "get_s3_client",
                        lambda: SimpleNamespace(generate_presigned_url=lambda *a, **k: "http://x/o.mov"))
    monkeypatch.setattr(osc_timecode.subprocess, "run",
                        lambda *a, **k: SimpleNamespace(stdout="\n00:59:55:00\n00:59:55:00\n"))
    assert osc_timecode.probe_start_tc("raw/k.mov") == "00:59:55:00"
    monkeypatch.setattr(osc_timecode.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout="garbage\n"))
    assert osc_timecode.probe_start_tc("raw/k.mov") is None
    assert osc_timecode.probe_start_tc(None) is None
