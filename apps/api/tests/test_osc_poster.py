"""OSC posters: the default thumbnail is a random GOOD frame after the slate, never the slate."""
import random

from packages.transcoder import osc_poster as op

N = op.W * op.H


def frame(fn):
    return bytes(max(0, min(255, int(fn(i % op.W, i // op.W)))) for i in range(N))


def test_window_skips_slate_and_head_tail():
    lo, hi = op.window(58.7)            # an OSC :53 spot + 5 s slate
    assert lo >= op.SLATE_SECONDS and abs(lo - 0.15 * 58.7) < 1e-6
    assert abs(hi - 0.85 * 58.7) < 1e-6
    assert op.window(None) is None and op.window(0.5) is None
    lo, hi = op.window(6.0)             # too short for a slate: plain 15–85%
    assert 0 < lo < hi < 6.0


def test_black_white_flat_and_soft_frames_are_rejected():
    assert not op.score_frame(frame(lambda x, y: 4))[0]            # near-black
    assert not op.score_frame(frame(lambda x, y: 250))[0]          # near-white
    assert not op.score_frame(frame(lambda x, y: 120 + x * 0.3))[0]  # flat / fade, low contrast
    assert not op.score_frame(frame(lambda x, y: 60 + x * 2))[0]   # smooth ramp: contrast, no detail


def test_a_detailed_mid_exposure_frame_is_accepted():
    rng = random.Random(7)
    ok, score, m = op.score_frame(frame(lambda x, y: 120 + rng.randint(-70, 70)))
    assert ok, m


def test_pick_rerolls_past_bad_frames(monkeypatch):
    seq = iter([frame(lambda x, y: 3), frame(lambda x, y: 252),
                frame(lambda x, y: 120 + ((x * 7 + y * 13) % 90) - 45)])
    monkeypatch.setattr(op, "_grab_gray", lambda url, t: next(seq))
    t = op.pick_poster_time("u", 60.0, rng=random.Random(1))
    assert op.SLATE_SECONDS <= t <= 51.0
