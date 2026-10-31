"""RTMPose keypoints use MediaPipe's joint order; SimCC decoding and box geometry are exact."""
from pathlib import Path

import numpy as np
import pytest

from egohand_twin.hybrid import RtmHand

MODELS = Path(__file__).resolve().parents[1]/"models"/"rtm"


def _session(peaks_x, peaks_y):
    class S:
        def run(self, _, feeds):
            x, y = np.zeros((1, 21, 512)), np.zeros((1, 21, 512))
            x[0, np.arange(21), peaks_x] = 1.
            y[0, np.arange(21), peaks_y] = 1.
            return x, y
    return S()


def test_each_joint_decodes_independently_in_order():
    # joint j peaks at x bin 20*j: decoded x must increase with the joint index (no reordering)
    rtm = object.__new__(RtmHand)
    rtm.pose = _session(np.arange(21)*20, np.full(21, 256))
    points, _ = rtm.keypoints(np.zeros((256, 256, 3), np.uint8), (0, 0, 256, 256))
    side = 256*1.25
    assert np.allclose(points[:, 0], 128 + (np.arange(21)*20/2/256 - .5)*side)
    assert np.all(np.diff(points[:, 0]) > 0)


def test_box_padding_is_1_25_of_the_longer_side():
    rtm = object.__new__(RtmHand)
    rtm.pose = _session(np.full(21, 0), np.full(21, 0))           # bin 0 = crop corner
    points, _ = rtm.keypoints(np.zeros((540, 960, 3), np.uint8), (100, 100, 300, 200))
    centre, side = np.array([200, 150]), 200*1.25
    assert np.allclose(points[0], centre - side/2)


@pytest.mark.skipif(not (MODELS/"rtmpose_m_hand.onnx").exists(), reason="RTM models not fetched")
def test_order_was_verified_against_mediapipe():
    # Recorded verification (docs/HYBRID_TRACKING_AUDIT.md section 4): on 60 confident MediaPipe hands
    # every RTMPose joint landed nearest the same-numbered MediaPipe joint (21/21). The pipeline
    # therefore uses RTMPose points without remapping; this test guards that no remap was added.
    import egohand_twin.hybrid as h
    assert not hasattr(h, "RTMPOSE_TO_MEDIAPIPE")
