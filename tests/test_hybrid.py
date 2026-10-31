from pathlib import Path

import numpy as np
import pytest

from egohand_twin.handfit import MEDIAN_HAND, fit_hand
from egohand_twin.hybrid import HybridDetector, RtmHand, _overlap
from egohand_twin.model import Detection

MODELS = Path(__file__).resolve().parents[1]/"models"/"rtm"


def _project(points3d, scale=900., offset=(400., 300.)):
    return points3d[:, :2]*scale + offset


def test_fit_keeps_the_detected_2d_points_and_adds_plausible_depth():
    rotated = MEDIAN_HAND @ np.array([[0, -1, 0], [1, 0, 0], [0, 0, 1.]]).T  # hand rotated in the image
    points = _project(rotated)
    world = fit_hand(points)
    assert world.shape == (21, 3) and np.isfinite(world).all()
    assert np.allclose(world.mean(0), 0, atol=1e-9)
    # x/y are the detected points (shifted and scaled), so the 2D shape is preserved exactly
    scaled = (points - points.mean(0))/900.
    assert np.allclose(world[:, :2], scaled, atol=2e-3)
    assert np.ptp(world[:, 2]) > .01  # depth borrowed from the median hand, not flat


def test_fit_rejects_points_that_are_not_a_hand():
    rng = np.random.default_rng(1)
    assert fit_hand(rng.uniform(0, 500, (21, 2))) is None
    assert fit_hand(np.full((21, 2), 7.)) is None


def test_overlap_is_relative_to_the_smaller_box():
    assert _overlap((0, 0, 10, 10), (5, 5, 15, 15)) == pytest.approx(.25)
    assert _overlap((0, 0, 10, 10), (2, 2, 4, 4)) == 1.
    assert _overlap((0, 0, 1, 1), (5, 5, 6, 6)) == 0.


def _hand(x, y, size=.08):
    image = np.zeros((21, 3))
    image[:, 0] = x + np.linspace(0, size, 21)
    image[:, 1] = y + np.linspace(0, size, 21)
    return Detection(image, np.zeros((21, 3)), "Left", .9)


def test_hybrid_skips_found_hands_and_falls_back_to_rtmpose_with_neutral_side():
    class Primary:
        def detect(self, rgb, t, full=None):
            return [_hand(.1, .1)]

        def close(self):
            pass

    class Reader:  # MediaPipe finds nothing inside the box
        def detect(self, rgb, t):
            return []

    class Rtm:
        def tiled_boxes(self, rgb):
            return [(96, 54, 180, 140, .9), (500, 300, 620, 420, .8)]  # first overlaps the found hand

        def keypoints(self, rgb, box):
            points = _project(MEDIAN_HAND @ np.diag([1, -1, 1.]), 700., (560., 360.))
            return points, np.full(21, .8)

    h = object.__new__(HybridDetector)
    h.primary, h.crop_reader, h.rtm, h.crop_retry = Primary(), Reader(), Rtm(), True
    h.num_hands, h.pose_threshold, h.fit_3d, h.max_boxes = 2, .45, True, 4
    h.gate_seconds, h.gate_diagonal, h.recent = .8, .15, [(-.1, np.array([560., 360.]))]
    h.stats = {"boxes": 0, "gated_out": 0, "mediapipe_in_box": 0, "rtmpose_fitted": 0, "rtmpose_rejected": 0}
    out = h.detect(np.zeros((540, 960, 3), np.uint8), 0.)
    assert len(out) == 2 and h.stats["boxes"] == 1
    added = out[1]
    assert added.origin == "hand_detector" and added.origin_detail == "rtmpose_fitted_3d"
    assert added.handedness_score == .5 and added.index == 1  # side left to the track vote


@pytest.mark.skipif(not (MODELS/"rtmdet_nano_hand.onnx").exists(), reason="RTM models not fetched")
def test_rtm_models_run_on_a_blank_frame():
    pytest.importorskip("onnxruntime")
    rtm = RtmHand(MODELS)
    assert rtm.tiled_boxes(np.full((540, 960, 3), 114, np.uint8)) == []  # featureless grey: no hand
    points, scores = rtm.keypoints(np.zeros((540, 960, 3), np.uint8), (100, 100, 200, 200, .9))
    assert points.shape == (21, 2) and scores.shape == (21,)
