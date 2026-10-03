"""OSC hover-scrub storyboards: sprite geometry + WebVTT cues (pure parts; ffmpeg not needed)."""
from packages.transcoder import osc_sprite as s


def test_keys_are_per_version():
    k = s.keys("abc")
    assert k == {"jpg": "osc/sprites/abc.jpg", "json": "osc/sprites/abc.json", "vtt": "osc/sprites/abc.vtt"}


def test_sharp_tiers_cover_dpr3_and_stay_under_ios_decode_limits():
    widths = sorted(w for w, _, _ in s.TIERS)
    assert widths[-1] >= 350 * 3          # a ~350-CSS-px phone card at DPR 3
    assert any(w >= 160 * 3 for w in widths)  # the 160-CSS seek tooltip at DPR 3
    for w, cols, rows in s.TIERS:
        h = round(w * 9 / 16)
        assert (w * cols) * (h * rows) <= 10.6e6, (w, cols, rows)


def test_tier_keys_are_per_version_and_numbered():
    assert s.tier_keys("v1", 1080, 3) == [
        "osc/sprites/v1/t1080_001.jpg", "osc/sprites/v1/t1080_002.jpg", "osc/sprites/v1/t1080_003.jpg"]


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
