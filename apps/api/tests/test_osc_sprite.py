"""OSC hover-scrub storyboards: sprite geometry + WebVTT cues (pure parts; ffmpeg not needed)."""
from packages.transcoder import osc_sprite as s


def test_keys_are_per_version():
    k = s.keys("abc")
    assert k == {"jpg": "osc/sprites/abc.jpg", "json": "osc/sprites/abc.json", "vtt": "osc/sprites/abc.vtt"}


def test_build_refuses_no_duration(tmp_path):
    assert s.build("u", 0, 1920, 1080, str(tmp_path)) is None


def test_vtt_cues_cover_the_whole_duration_on_the_grid():
    meta = {"count": 59, "cols": 10, "rows": 6, "tile_w": 160, "tile_h": 90, "interval": 58.68 / 59, "duration": 58.68}
    v = s.vtt(meta, "osc_sprite.jpg").splitlines()
    assert v[0] == "WEBVTT"
    cues = [l for l in v if "#xywh=" in l]
    assert len(cues) == 59
    assert cues[0].endswith("#xywh=0,0,160,90")
    assert cues[10].endswith("#xywh=0,90,160,90")       # 11th frame wraps to row 2
    assert cues[58].endswith("#xywh=1280,450,160,90")   # last: col 8, row 5
    times = [l for l in v if "-->" in l]
    assert times[0].startswith("00:00:00.000") and times[-1].endswith("00:00:58.680")
