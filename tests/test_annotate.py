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


def _labels_file(tmp_path):
    data = {"schema_version": "2.0", "source_sha256": "x", "reviewed": False, "frames": [
        {"frame_index": 2, "timestamp_s": .2, "split": "dev", "complete": True, "hands": [
            {"gt_id": "a:L", "side": "wearer_left", "wrist_xy": [.3, .6], "wrist_in_frame": True,
             "visibility": "full", "tags": []},
            {"gt_id": "a:R", "side": "wearer_right", "wrist_xy": [.7, .6], "wrist_in_frame": True,
             "visibility": "occluded", "tags": ["cloth"]}]},
        {"frame_index": 5, "timestamp_s": .5, "split": "dev", "complete": True, "hands": []}]}
    path = tmp_path/"labels.json"
    path.write_text(json.dumps(data))
    return path


def _video(tmp_path, n=8):
    video = tmp_path/"clip.avi"
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"MJPG"), 10, (160, 90))
    for i in range(n):
        writer.write(np.full((90, 160, 3), 30*i % 255, np.uint8))
    writer.release()
    return video


def _fill(csv_path, decisions):
    import csv
    rows = list(csv.DictReader(csv_path.open()))
    for row in rows:
        row.update(decisions.get((row["frame_index"], row["gt_id"]), {}))
    with csv_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


def test_review_pack_and_complete_review_marks_reviewed(tmp_path):
    from egohand_twin.annotate import apply_label_review, label_review_pack
    labels = _labels_file(tmp_path)
    info = label_review_pack(_video(tmp_path), labels, tmp_path/"review")
    assert info == {"frames": 2, "rows": 3, "sheets": 1, "out": str(tmp_path/"review")}
    csv_path = tmp_path/"review"/"review.csv"
    _fill(csv_path, {("2", "a:L"): {"decision": "ok"},
                     ("2", "a:R"): {"decision": "fix", "corrected_side": "wearer_left",
                                    "corrected_wrist_x": "0.72", "corrected_wrist_y": "1.02"}})
    result = apply_label_review(labels, csv_path, "UB", tmp_path/"reviewed.json")
    assert result["reviewed"] is True and result["decisions"]["fix"] == 1
    out = json.loads((tmp_path/"reviewed.json").read_text())
    fixed = out["frames"][0]["hands"][1]
    assert fixed["side"] == "wearer_left" and fixed["wrist_xy"] == [.72, 1.02] and fixed["wrist_in_frame"] is False
    assert out["reviewed"] is True and out["review"]["reviewer"] == "UB"
    assert json.loads(labels.read_text())["reviewed"] is False  # input untouched


def test_incomplete_or_invalid_review_stays_provisional(tmp_path):
    from egohand_twin.annotate import apply_label_review, label_review_pack
    labels = _labels_file(tmp_path)
    label_review_pack(_video(tmp_path), labels, tmp_path/"review")
    csv_path = tmp_path/"review"/"review.csv"
    _fill(csv_path, {("2", "a:L"): {"decision": "unsure"}, ("2", "a:R"): {"decision": "ok"},
                     ("5", ""): {"missing_hand_note": "hand at bottom left"}})
    result = apply_label_review(labels, csv_path, "UB", tmp_path/"r.json")
    assert result["reviewed"] is False and len(result["open_items"]) == 2
    _fill(csv_path, {("2", "a:R"): {"decision": "fix", "corrected_side": "left"}})
    with pytest.raises(ValueError, match="corrected_side"):
        apply_label_review(labels, csv_path, "UB", tmp_path/"r2.json")
    with pytest.raises(ValueError, match="never overwritten"):
        apply_label_review(labels, csv_path, "UB", tmp_path/"r.json")
