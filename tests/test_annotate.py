import json

import cv2
import numpy as np
import pytest

from egohand_twin.annotate import make_annotation_set, parse_intervals


def test_parse_intervals_validates():
    assert parse_intervals("0:12,60:72") == [(0., 12.), (60., 72.)]
    with pytest.raises(ValueError):
        parse_intervals("5:2")


def test_annotation_set_keeps_split_and_source_frame_indices(tmp_path):
    video = tmp_path/"clip.avi"
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"MJPG"), 10, (64, 48))
    for i in range(30):
        writer.write(np.full((48, 64, 3), i*8, np.uint8))
    writer.release()
    timestamps = [i/10 for i in range(30)]
    template = make_annotation_set(video, tmp_path/"out", timestamps, [(1., 2.), (2.5, 3.)], 3, "holdout")
    indices = [f["frame_index"] for f in template["frames"]]
    assert indices == [10, 13, 16, 19, 25, 28]
    assert {f["split"] for f in template["frames"]} == {"holdout"}
    assert template["reviewed"] is False and template["schema_version"] == "2.0"
    assert all(f["complete"] is False for f in template["frames"])
    saved = json.loads((tmp_path/"out"/"labels.template.json").read_text())
    assert saved["frames"][0]["timestamp_s"] == pytest.approx(1.0)
    assert (tmp_path/"out"/"frames"/"frame_000025.jpg").exists()
