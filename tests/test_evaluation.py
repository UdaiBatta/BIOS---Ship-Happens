import json

import pytest

from egohand_twin.evaluation import evaluate


def test_predicted_hands_do_not_inflate_recall(tmp_path):
    (tmp_path/"COMPLETE").touch()
    (tmp_path/"manifest.json").write_text(json.dumps({"source": {
        "sha256": "test", "width": 100, "height": 100}}))
    frames = [
        {"frame_index": 0, "hands": [{"track_id": 1, "observed": True,
                                      "image_xyz_raw": [[.2, .5, 0]]*21}]},
        {"frame_index": 1, "hands": [{"track_id": 1, "observed": False,
                                      "image_xyz_raw": None}]},
        {"frame_index": 2, "hands": [{"track_id": 2, "observed": True,
                                      "image_xyz_raw": [[.2, .5, 0]]*21}]},
    ]
    (tmp_path/"landmarks.jsonl").write_text("\n".join(json.dumps(f) for f in frames))
    labels = tmp_path/"labels.json"
    labels.write_text(json.dumps({"source_sha256": "test", "reviewed": True, "frames": [
        {"frame_index": i, "hands": [{"identity": "worker_left", "wrist_xy": [.2, .5]}]}
        for i in range(3)]}))
    result = evaluate(tmp_path, labels)
    assert result["recall"] == pytest.approx(2/3)
    assert result["false_negatives"] == 1
    assert result["sampled_identity_switches"] == 1
    assert result["3d_error"] is None


def test_wrong_clip_labels_rejected(tmp_path):
    (tmp_path/"COMPLETE").touch()
    (tmp_path/"manifest.json").write_text('{"source":{"sha256":"clip_a"}}')
    labels = tmp_path/"labels.json"
    labels.write_text('{"source_sha256":"clip_b","frames":[]}')
    with pytest.raises(ValueError, match="source_sha256"):
        evaluate(tmp_path, labels)


def test_unreviewed_template_rejected(tmp_path):
    (tmp_path/"COMPLETE").touch()
    (tmp_path/"manifest.json").write_text('{"source":{"sha256":"test"}}')
    labels = tmp_path/"labels.json"
    labels.write_text('{"source_sha256":"test","reviewed":false,"frames":[]}')
    with pytest.raises(ValueError, match="manually reviewed"):
        evaluate(tmp_path, labels)
