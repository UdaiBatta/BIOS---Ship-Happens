"""Crop and tile coordinates map back to the full frame exactly (Test 4 groundwork)."""
from pathlib import Path

import numpy as np

from motioniq.hybrid import RtmHand
from motioniq.model import Detection, map_crop_detection, square_box


def test_crop_detection_maps_back_to_full_frame():
    image = np.zeros((21, 3))
    image[:, 0], image[:, 1] = .5, .25                  # centre-top of the crop
    d = Detection(image, np.zeros((21, 3)), "Left", .9)
    m = map_crop_detection(d, (100, 50, 300, 250), 960, 540)
    assert np.allclose(m.image[0, :2], [(100 + .5*200)/960, (50 + .25*200)/540])


def test_square_box_stays_inside_the_image_at_the_edge():
    x0, y0, x1, y1 = square_box(950, 530, 200, 960, 540)
    assert x1 - x0 == y1 - y0 == 200 and 0 <= x0 and x1 <= 960 and 0 <= y0 and y1 <= 540


def test_tiled_boxes_are_offset_into_frame_pixels():
    rtm = object.__new__(RtmHand)
    rtm.tiles, rtm.box_threshold = 4, .2
    calls = []

    def boxes(tile):
        calls.append(tile.shape)
        return [(10., 20., 30., 40., .9)] if len(calls) == 4 else []   # only the bottom-right tile fires
    rtm.boxes = boxes
    out = rtm.tiled_boxes(np.zeros((540, 960, 3), np.uint8))
    tw, th = 960//2 + 960//8, 540//2 + 540//8
    assert out == [(10. + 960 - tw, 20. + 540 - th, 30. + 960 - tw, 40. + 540 - th, .9)]


def test_rtmpose_keypoints_map_from_model_bins_to_frame_pixels():
    rtm = object.__new__(RtmHand)

    class Session:  # SimCC peaks at bin 256 (= pixel 128 of the 256 crop = crop centre) for every joint
        def run(self, _, feeds):
            x = np.zeros((1, 21, 512))
            x[0, :, 256] = 1.
            return x, x.copy()
    rtm.pose = Session()
    points, scores = rtm.keypoints(np.zeros((540, 960, 3), np.uint8), (400, 200, 500, 300))
    assert np.allclose(points, [450, 250]) and np.allclose(scores, 1.)  # the box centre in frame pixels
