import numpy as np
import pytest

from egohand_twin.model import (Detection, MultiViewDetector, is_duplicate, map_crop_detection,
                                square_box, tile_boxes)

W, H = 1920, 1080


def hand(x, y, size=.05, side="Left", origin="full_frame", spread=1.):
    """Synthetic hand in normalized coords: wrist at (x, y), fingers upwards."""
    image = np.zeros((21, 3))
    image[:, 0] = x + np.linspace(-size/2, size/2, 21)*spread
    image[:, 1] = y - np.abs(np.linspace(-1, 1, 21))*0 - np.linspace(0, size*1.6, 21)
    image[0, :2] = [x, y]
    world = (image - image.mean(axis=0))*.2
    return Detection(image, world, side, .9, 0, origin)


def test_full_resolution_crop_mapping_and_depth_scaling():
    d = hand(.5, .5)
    d.image[:, 2] = -.2
    box = (480, 270, 1290, 1080)  # 810 px square in a 1920x1080 frame
    mapped = map_crop_detection(d, box, W, H, "tile_1")
    assert mapped.image[0, 0] == pytest.approx((.5*810+480)/W)
    assert mapped.image[0, 1] == pytest.approx((.5*810+270)/H)
    assert mapped.image[0, 2] == pytest.approx(-.2*810/W)
    np.testing.assert_array_equal(mapped.world, d.world)
    assert mapped.origin == "tile_1"


def test_same_hand_from_two_crops_is_duplicate_but_adjacent_hands_are_not():
    a = hand(.45, .87)
    jitter = hand(.452, .868)
    neighbour = hand(.53, .91)  # two hands gripping one slab, ~155 px apart
    assert is_duplicate(a, jitter, W, H)
    assert not is_duplicate(a, neighbour, W, H)
    # The historical wrist rule (0.10 normalized) merges the adjacent real hands.
    assert is_duplicate(a, neighbour, W, H, policy="wrist")


def test_crossing_hands_with_different_pose_not_merged():
    a = hand(.40, .60, size=.08)
    b = hand(.42, .62, size=.08)
    b.image[:, :2] = b.image[0, :2] + (b.image[:, :2]-b.image[0, :2])*[-1, -1]  # opposite orientation
    assert not is_duplicate(a, b, W, H)


def test_boxes_stay_inside_frame():
    assert square_box(10, 10, 400, W, H) == (0, 0, 400, 400)
    assert square_box(1910, 1070, 400, W, H) == (1520, 680, 1920, 1080)
    assert square_box(960, 540, 5000, W, H) == (420, 0, 1500, 1080)
    tiles = tile_boxes(W, H, 3, .75)
    assert tiles[0] == (0, 270, 810, 1080) and tiles[-1] == (1110, 270, 1920, 1080)
    assert all(x1 <= W and y1 <= H for _, _, x1, y1 in tiles)


class FakeDetector:
    def __init__(self, outputs):
        self.outputs = outputs  # callable(image, t) -> list[Detection]
        self.calls = []

    def detect(self, image, t):
        self.calls.append((image.shape, t))
        return self.outputs(image, t)

    def close(self):
        pass


def make_detector(primary, secondary, **kw):
    d = MultiViewDetector.__new__(MultiViewDetector)
    defaults = dict(num_hands=2, strategies=["guided"], max_crops=4, dedupe="landmarks",
                    guided_scale=2.5, guided_min_px=320, guided_gap_s=.5, guided_anchor_s=1.,
                    guided_gate=.08, tile_count=3, tile_fraction=.75, memory=[], crop_max_side=None,
                    stats={"crops": 0, "frames_with_crops": 0, "accepted": {}, "duplicates": 0,
                           "guided_rejected_gate": 0, "memory_expired": 0})
    defaults.update(kw)
    d.__dict__.update(defaults)
    d.primary, d.secondary = FakeDetector(primary), FakeDetector(secondary)
    return d


def crop_relative(target_x, target_y):
    """Secondary detector that returns a hand at a fixed SOURCE position for any crop."""
    state = {}

    def run(image, t):
        box = state["box"]
        x0, y0, x1, y1 = box
        cx = (target_x*W - x0)/(x1-x0)
        cy = (target_y*H - y0)/(y1-y0)
        return [hand(cx, cy, size=.05*W/(x1-x0))]
    return run, state


def test_guided_crop_cannot_confirm_itself_beyond_anchor_age():
    full = np.zeros((H, W, 3), np.uint8)
    small = np.zeros((540, 960, 3), np.uint8)
    seen = {"t": 0.}

    def primary(image, t):
        return [hand(.3, .7)] if t == 0. else []

    def secondary(image, t):
        # Always "finds" a hand in the centre of whatever crop it is given.
        return [hand(.5, .55, size=.1)]
    d = make_detector(primary, secondary)
    assert len(d.detect(small, 0., full)) == 1
    origins = []
    for t in np.arange(1, 40)/30:
        out = d.detect(small, float(t), full)
        origins.append([o.origin for o in out])
    guided_frames = [i for i, o in enumerate(origins) if "guided_crop" in o]
    assert guided_frames, "guided crops should recover the missing hand briefly"
    last_time = (max(guided_frames)+1)/30
    assert last_time <= 1. + 1e-9, "no guided detection after the anchor age without confirmation"
    assert not d.memory


def test_guided_gate_rejects_far_candidates_and_crop_budget():
    full = np.zeros((H, W, 3), np.uint8)
    small = np.zeros((540, 960, 3), np.uint8)

    def primary(image, t):
        return [hand(.3, .7)] if t == 0. else []

    def secondary(image, t):
        return [hand(.05, .05)]  # corner of the crop: far from the tracked wrist
    d = make_detector(primary, secondary, strategies=["guided", "tiles"], max_crops=2)
    d.detect(small, 0., full)
    before = len(d.secondary.calls)
    out = d.detect(small, 1/30, full)
    assert out == [] or all(o.origin != "guided_crop" for o in out)
    assert d.stats["guided_rejected_gate"] >= 1
    assert len(d.secondary.calls) - before <= 2
