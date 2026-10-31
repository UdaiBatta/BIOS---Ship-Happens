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


def _v2_run(tmp_path, pred_frames):
    (tmp_path/"COMPLETE").touch()
    (tmp_path/"manifest.json").write_text(json.dumps({"source": {
        "sha256": "test", "width": 100, "height": 100}}))
    (tmp_path/"landmarks.jsonl").write_text("\n".join(json.dumps(f) for f in pred_frames))


def _hand(track, x, y, side="Left", observed=True, origin="full_frame"):
    return {"track_id": track, "observed": observed, "side": side, "raw_side": side,
            "detection_origin": origin if observed else None,
            "image_xyz_raw": [[x, y, 0]]*21 if observed else None}


def _labels(tmp_path, frames, reviewed=False):
    path = tmp_path/"labels.json"
    path.write_text(json.dumps({"schema_version": "2.0", "source_sha256": "test",
                                "reviewed": reviewed, "frames": frames}))
    return path


def test_v2_provisional_requires_flag_and_is_stamped(tmp_path):
    _v2_run(tmp_path, [{"frame_index": 0, "hands": []}])
    labels = _labels(tmp_path, [{"frame_index": 0, "split": "dev", "complete": True, "hands": []}])
    with pytest.raises(ValueError, match="allow-provisional"):
        evaluate(tmp_path, labels)
    result = evaluate(tmp_path, labels, allow_provisional=True)
    assert result["label_status"] == "provisional"
    assert any("PROVISIONAL" in note for note in result["limitations"])


def test_v1_labels_cannot_bypass_review_with_provisional_flag(tmp_path):
    _v2_run(tmp_path, [{"frame_index": 0, "hands": []}])
    labels = tmp_path/"labels.json"
    labels.write_text('{"source_sha256":"test","reviewed":false,"frames":[{"frame_index":0,"hands":[]}]}')
    with pytest.raises(ValueError, match="manually reviewed"):
        evaluate(tmp_path, labels, allow_provisional=True)


def test_v2_split_groups_side_accuracy_and_out_of_frame_wrist(tmp_path):
    _v2_run(tmp_path, [
        {"frame_index": 0, "hands": [_hand(1, .2, .5, "Left"), _hand(2, .8, .5, "Left")]},
        {"frame_index": 1, "hands": [_hand(1, .2, .5, "Left", observed=False), _hand(3, .5, .2)]},
        {"frame_index": 2, "hands": [_hand(4, .2, .98, "Left")]},
    ])
    labels = _labels(tmp_path, [
        {"frame_index": 0, "split": "dev", "interval": "a", "hands": [
            {"gt_id": "a:L", "side": "wearer_left", "wrist_xy": [.2, .5], "visibility": "full"},
            {"gt_id": "a:R", "side": "wearer_right", "wrist_xy": [.8, .5], "visibility": "occluded"}]},
        {"frame_index": 1, "split": "dev", "interval": "a", "hands": [
            {"gt_id": "a:L", "side": "wearer_left", "wrist_xy": [.2, .5], "visibility": "full"}]},
        {"frame_index": 2, "split": "holdout", "interval": "b", "hands": [
            {"gt_id": "b:L", "side": "wearer_left", "wrist_xy": [.2, 1.02], "wrist_in_frame": False,
             "visibility": "truncated", "tags": ["edge"]}]},
    ])
    r = evaluate(tmp_path, labels, allow_provisional=True)
    # Frame 1: predicted (unobserved) track does not count; the far hand is a false positive.
    assert (r["true_positives"], r["false_negatives"], r["false_positives"]) == (3, 1, 1)
    assert r["recall_by_group"]["split=dev"]["matched"] == 2
    assert r["recall_by_group"]["visibility=truncated"]["matched"] == 1
    side = r["side_accuracy_raw_per_frame"]["all"]
    assert side["accuracy_as_labeled"]["k"] == 2 and side["accuracy_as_labeled"]["n"] == 3
    assert side["confusion"]["wearer_right->Left"] == 1
    dev_only = evaluate(tmp_path, labels, allow_provisional=True, split="dev")
    assert dev_only["labeled_frames"] == 2


def test_wrist_outside_image_requires_flag(tmp_path):
    _v2_run(tmp_path, [{"frame_index": 0, "hands": []}])
    labels = _labels(tmp_path, [{"frame_index": 0, "split": "dev", "hands": [
        {"gt_id": "x", "side": "unknown", "wrist_xy": [.5, 1.05], "visibility": "truncated"}]}])
    with pytest.raises(ValueError, match="wrist_in_frame"):
        evaluate(tmp_path, labels, allow_provisional=True)


def test_incomplete_frame_rejected(tmp_path):
    _v2_run(tmp_path, [{"frame_index": 0, "hands": []}])
    labels = _labels(tmp_path, [{"frame_index": 0, "split": "dev", "complete": False, "hands": []}])
    with pytest.raises(ValueError, match="not marked complete"):
        evaluate(tmp_path, labels, allow_provisional=True)


def test_offline_track_vote_reported_and_unknown_not_forced(tmp_path):
    from egohand_twin.identity import write_identity
    frames = []
    for i in range(6):
        # Track 1: mostly Left with one flipped frame; track 2: ambiguous.
        left = {**_hand(1, .2, .5, "Right" if i == 2 else "Left"), "handedness_score": .9}
        ambiguous = {**_hand(2, .8, .5, "Right" if i % 2 else "Left"), "handedness_score": .55}
        frames.append({"frame_index": i, "timestamp_s": i/30, "hands": [left, ambiguous]})
    _v2_run(tmp_path, frames)
    write_identity(tmp_path)
    votes = json.loads((tmp_path/"identity.json").read_text())["tracks"]
    assert votes["1"]["side_vote"] == "Left" and votes["2"]["side_vote"] == "unknown"
    labels = _labels(tmp_path, [{"frame_index": 2, "split": "dev", "interval": "a", "hands": [
        {"gt_id": "a:L", "side": "wearer_left", "wrist_xy": [.2, .5], "visibility": "full"},
        {"gt_id": "a:R", "side": "wearer_right", "wrist_xy": [.8, .5], "visibility": "full"}]}])
    r = evaluate(tmp_path, labels, allow_provisional=True)
    assert r["side_accuracy_raw_per_frame"]["all"]["accuracy_as_labeled"]["k"] == 0  # frame 2: L flipped to Right, R reported Left
    vote = r["side_accuracy_offline_track_vote"]["all"]
    assert vote["accuracy_as_labeled"]["k"] == 1 and vote["confusion"]["wearer_right->unknown"] == 1


def test_missing_reason_claims_checked_against_undetected_labeled_hands(tmp_path):
    out = {"track_id": 1, "observed": False, "state": "lost", "side": "Left",
           "missing_reason": "out_of_view", "image_xyz_raw": None}
    unk = {"track_id": 2, "observed": False, "state": "lost", "side": "Left",
           "missing_reason": "unknown", "image_xyz_raw": None}
    _v2_run(tmp_path, [
        {"frame_index": 0, "hands": [_hand(1, .2, .5), _hand(2, .8, .5)]},
        {"frame_index": 1, "hands": [out, unk]},
    ])
    labels = _labels(tmp_path, [{"frame_index": 1, "split": "dev", "hands": [
        {"gt_id": "a", "side": "wearer_left", "wrist_xy": [.22, .5], "visibility": "occluded"}]}])
    check = evaluate(tmp_path, labels, allow_provisional=True)["missing_reason_check"]
    # The "out_of_view" track's hand is still visible (labeled) near its last wrist: contradicted.
    assert check["out_of_view"] == {"claims": 1, "contradicted_by_nearby_undetected_hand": 1}
    assert check["unknown"] == {"records": 1, "with_nearby_undetected_hand": 0}
