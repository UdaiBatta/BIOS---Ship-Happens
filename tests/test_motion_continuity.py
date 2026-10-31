"""One Euro smoothing: less jitter when still, follows real motion, resets after gaps, per track."""
import numpy as np

from egohand_twin.model import Detection
from egohand_twin.tracking import IdentityTracker, OneEuro


def test_jitter_reduced_on_a_still_point():
    rng = np.random.default_rng(0)
    f = OneEuro()
    raw = .5 + rng.normal(0, .003, 120)
    smooth = np.array([f(np.array([v]), i/30)[0] for i, v in enumerate(raw)])
    assert np.std(np.diff(smooth[10:])) < .5*np.std(np.diff(raw[10:]))


def test_fast_motion_is_followed_with_bounded_lag():
    # Measured with the default filter (min_cutoff 1.7, beta 0.03): at 0.6 frame widths per second
    # the smoothed point trails by ~0.056 widths, i.e. ~0.09 s (about 3 frames). Reported in
    # docs/PERFORMANCE_REPORT.md; raw landmarks are always kept alongside (image_xyz_raw).
    f = OneEuro()
    speed = .6
    xs = np.linspace(0, speed, 31)
    out = [f(np.array([x]), i/30)[0] for i, x in enumerate(xs)]
    lag_s = (xs[-1] - out[-1])/speed
    assert 0 <= lag_s < .12


def test_filter_resets_after_a_gap():
    f = OneEuro()
    f(np.array([.1]), 0.)
    assert f(np.array([.9]), 1.)[0] == .9            # > 0.2 s gap: no smoothing across it


def test_two_hands_are_smoothed_independently():
    def hand(x):
        image = np.zeros((21, 3))
        image[:, 0] = x + np.linspace(0, .05, 21)
        image[:, 1] = .5
        return Detection(image, np.zeros((21, 3)), "Right", .9)
    t = IdentityTracker()
    for i in range(10):
        out = t.update([hand(.2), hand(.7)], i/30)
    xs = sorted(r["image_xyz"][0][0] for r in out if r["observed"])
    assert abs(xs[0] - .2) < 1e-6 and abs(xs[1] - .7) < 1e-6   # no blending between identities
