import json

import pytest

from egohand_twin.conditions import apply_conditions, condition_at, template, validate_conditions
from egohand_twin.evaluation import evaluate
from egohand_twin.schema import validate_jsonl


def interval(start, end, **over):
    item = {"start_s": start, "end_s": end, "glove_ppe": "none", "occlusion": "partial", "lighting": "ok",
            "excluded": False, "exclusion_reason": None, "reviewer": None, "note": ""}
    item.update(over)
    return item


def conditions(*items, source="test"):
    data = template(source)
    data["intervals"] = list(items)
    return data


def test_valid_intervals_and_lookup():
    items = validate_conditions(conditions(interval(1., 2., lighting="harsh"), interval(0., 1.)), "test")
    assert [i["start_s"] for i in items] == [0., 1.]
    assert condition_at(items, 1.)["lighting"] == "harsh"   # start inclusive
    assert condition_at(items, 2.) is None                  # end exclusive


@pytest.mark.parametrize("item,message", [
    (interval(0., 1., excluded=True), "requires an exclusion_reason"),
    (interval(0., 1., exclusion_reason="blur"), "excluded=false"),
    (interval(0., 1., occlusion="some"), "occlusion"),
    (interval(0., 1., lighting="bright"), "lighting"),
    (interval(1., 1.), "before end_s"),
    (interval(0., 1., worker="A"), "unknown fields"),
])
def test_invalid_intervals_rejected(item, message):
    with pytest.raises(ValueError, match=message):
        validate_conditions(conditions(item), "test")


def test_overlap_and_wrong_source_rejected():
    with pytest.raises(ValueError, match="overlap"):
        validate_conditions(conditions(interval(0., 2.), interval(1., 3.)), "test")
    with pytest.raises(ValueError, match="different source"):
        validate_conditions(conditions(interval(0., 1.)), "other")


def make_run(tmp_path):
    run = tmp_path/"run"
    run.mkdir()
    (run/"COMPLETE").touch()
    (run/"manifest.json").write_text(json.dumps({"source": {"sha256": "test", "width": 100, "height": 100}}))
    hand = {"track_id": 1, "state": "observed", "observed": True, "side": "Left", "raw_side": "Left",
            "anatomical_side": "unknown", "detection_origin": "full_frame",
            "image_xyz_raw": [[.2, .5, 0]]*21}
    frames = [{"frame_index": i, "timestamp_s": float(i), "source_pts_s": float(i),
               "hands": [hand] if i != 1 else []} for i in range(3)]
    (run/"landmarks.jsonl").write_text("\n".join(json.dumps(f) for f in frames)+"\n")
    labels = tmp_path/"labels.json"
    labels.write_text(json.dumps({"schema_version": "2.0", "source_sha256": "test", "reviewed": False,
                                  "frames": [{"frame_index": i, "split": "dev", "hands": [
                                      {"gt_id": "a", "side": "wearer_left", "wrist_xy": [.2, .5],
                                       "visibility": "full"}]} for i in range(3)]}))
    return run, labels


def test_evaluation_excludes_and_slices_by_condition(tmp_path):
    run, labels = make_run(tmp_path)
    path = tmp_path/"conditions.json"
    path.write_text(json.dumps(conditions(
        interval(0., 1., occlusion="none"),
        interval(1., 2., excluded=True, exclusion_reason="camera covered"),
        interval(2., 3., occlusion="heavy"))))
    plain = evaluate(run, labels, allow_provisional=True, split="dev")
    assert (plain["true_positives"], plain["false_negatives"]) == (2, 1)
    assert plain["split_filter"] == "dev"
    r = evaluate(run, labels, allow_provisional=True, conditions=path)
    assert r["split_filter"] is None
    assert (r["true_positives"], r["false_negatives"]) == (2, 0)  # frame 1 excluded, not a miss
    assert r["excluded_by_conditions"] == {"frames": 1, "labeled_hands": 1, "reasons": {"camera covered": 1}}
    assert r["recall_by_group"]["condition.occlusion=heavy"]["matched"] == 1


def test_apply_writes_schema_valid_copy_without_touching_input(tmp_path):
    run, _ = make_run(tmp_path)
    path = tmp_path/"conditions.json"
    path.write_text(json.dumps(conditions(interval(0., 1., lighting="harsh"),
                                          interval(1., 2., excluded=True, exclusion_reason="lens smudge"))))
    original = (run/"landmarks.jsonl").read_text()
    out = apply_conditions(run, path)
    assert (run/"landmarks.jsonl").read_text() == original
    rows = [json.loads(line) for line in out.read_text().splitlines()]
    assert rows[0]["quality"]["conditions"]["lighting"] == "harsh"
    assert rows[1]["quality"]["excluded"] and rows[1]["quality"]["exclusion_reason"] == "lens smudge"
    assert rows[2]["quality"]["conditions_source"] == "not annotated"
    assert validate_jsonl(out)["valid"]
    with pytest.raises(ValueError, match="never overwritten"):
        apply_conditions(run, path)
