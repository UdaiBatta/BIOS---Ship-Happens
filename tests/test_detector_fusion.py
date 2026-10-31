"""Hybrid fusion: duplicates are skipped, recovery is track-gated, crop retry is opt-in."""
import numpy as np

from egohand_twin.handfit import MEDIAN_HAND
from egohand_twin.hybrid import HybridDetector
from egohand_twin.model import Detection


def _hand(x, y=.5, size=.08):
    image = np.zeros((21, 3))
    image[:, 0] = x + np.linspace(0, size, 21)
    image[:, 1] = y + np.linspace(0, size, 21)
    return Detection(image, np.zeros((21, 3)), "Left", .9)


class Primary:
    def __init__(self, frames):
        self.frames = frames

    def detect(self, rgb, t, full=None):
        return list(self.frames.pop(0))

    def close(self):
        pass


class Rtm:
    def __init__(self, box, wrist):
        self.box, self.wrist = box, np.array(wrist, float)

    def tiled_boxes(self, rgb):
        return [self.box]

    def keypoints(self, rgb, box):
        pts = MEDIAN_HAND[:, :2]*700
        return pts - pts[0] + self.wrist, np.full(21, .5)


def _hybrid(frames, box, wrist):
    h = object.__new__(HybridDetector)
    h.primary, h.rtm, h.crop_retry, h.crop_reader = Primary(frames), Rtm(box, wrist), False, None
    h.num_hands, h.pose_threshold, h.fit_3d, h.max_boxes = 2, .25, True, 4
    h.gate_seconds, h.gate_diagonal, h.recent = .8, .15, []
    h.stats = {"boxes": 0, "gated_out": 0, "mediapipe_in_box": 0, "rtmpose_fitted": 0, "rtmpose_rejected": 0}
    return h


def test_hand_seen_recently_and_missing_now_is_recovered_by_rtmpose():
    rgb = np.zeros((540, 960, 3), np.uint8)
    h = _hybrid([[_hand(.5, .5)], []], (460, 250, 560, 350, .9), (480, 270))
    assert len(h.detect(rgb, 0.)) == 1                        # MediaPipe sees it
    out = h.detect(rgb, 1/30)                                 # MediaPipe misses it: recovered
    assert len(out) == 1 and out[0].origin_detail == "rtmpose_fitted_3d" and out[0].handedness_score == .5


def test_candidate_far_from_any_recent_hand_is_gated_out():
    rgb = np.zeros((540, 960, 3), np.uint8)
    h = _hybrid([[_hand(.1, .2)], []], (800, 400, 900, 500, .9), (820, 420))
    h.detect(rgb, 0.)
    assert h.detect(rgb, 1/30) == [] and h.stats["gated_out"] == 1


def test_no_recovery_without_any_recent_hand():
    rgb = np.zeros((540, 960, 3), np.uint8)
    h = _hybrid([[]], (460, 250, 560, 350, .9), (480, 270))
    assert h.detect(rgb, 0.) == [] and h.stats["boxes"] == 0


def test_box_on_an_already_found_hand_is_not_used_again():
    rgb = np.zeros((540, 960, 3), np.uint8)
    found = _hand(.5, .5, size=.1)
    h = _hybrid([[found], [found]], (480, 270, 576, 324, .9), (490, 280))
    h.detect(rgb, 0.)
    h.recent.append((0., np.array([100., 100.])))               # another hand is missing elsewhere
    out = h.detect(rgb, 1/30)
    assert len(out) == 1 and h.stats["boxes"] == 0            # the box overlaps the found hand: skipped
