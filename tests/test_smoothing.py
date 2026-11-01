"""Offline smoothing: no lag on fast motion, less jitter when still, per track, raw untouched."""
import numpy as np

from egohand_twin.smoothing import rts_wrist, smooth_samples


def _hand(track, x, y, observed=True):
    image = np.zeros((21, 3))
    image[:, 0], image[:, 1] = x + np.linspace(0, .02, 21), y
    return {"track_id": track, "observed": observed, "image_xyz_raw": image.tolist(), "image_xyz": image.tolist(),
            "world_xyz_m_raw": np.zeros((21, 3)).tolist(), "world_xyz_m": np.zeros((21, 3)).tolist()}


def test_rts_follows_fast_motion_without_lag():
    t = np.arange(30)/30
    path = np.stack([100 + 900*t, np.full(30, 500.)], 1)            # 900 px/s
    assert np.max(np.abs(rts_wrist(t, path) - path)) < 2.


def test_rts_reduces_jitter_on_a_still_wrist():
    rng = np.random.default_rng(0)
    t = np.arange(60)/30
    noisy = np.array([500., 500.]) + rng.normal(0, 4, (60, 2))
    out = rts_wrist(t, noisy)
    jitter = lambda a: np.mean(np.linalg.norm(a[2:] - 2*a[1:-1] + a[:-2], axis=1))
    assert jitter(out) < .5*jitter(noisy)


def test_smoothing_is_per_track_keeps_raw_and_stops_at_gaps():
    rng = np.random.default_rng(1)
    samples = []
    for i in range(40):
        hands = [_hand(1, .3 + rng.normal(0, .003), .5), _hand(2, .7 + rng.normal(0, .003), .5)]
        if 18 <= i < 22:
            hands[0] = {**hands[0], "observed": False, "image_xyz_raw": None}
        samples.append({"timestamp_s": i/30, "hands": hands})
    raw_before = [h["image_xyz_raw"] for s in samples for h in s["hands"]]
    n = smooth_samples(samples, 1920, 1080)
    assert n == 76                                                    # 80 hands minus 4 unobserved
    assert [h["image_xyz_raw"] for s in samples for h in s["hands"]] == raw_before
    xs = {k: [s["hands"][k]["image_xyz"][0][0] for s in samples if s["hands"][k]["observed"]] for k in (0, 1)}
    assert abs(np.mean(xs[0]) - .3) < .01 and abs(np.mean(xs[1]) - .7) < .01   # tracks never mixed
