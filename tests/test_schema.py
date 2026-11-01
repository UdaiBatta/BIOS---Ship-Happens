import json

import numpy as np
import pytest

from motioniq.identity import write_identity_jsonl
from motioniq.model import Detection, map_crop_detection
from motioniq.schema import load_schema, validate_jsonl
from motioniq.tracking import IdentityTracker, baseline_records
from jsonschema import Draft202012Validator


def det(x=.4, side="Left", origin="full_frame", detail=None):
    image = np.zeros((21, 3))
    image[:, 0] = x + np.linspace(0, .05, 21)
    image[:, 1] = .5 - np.linspace(0, .1, 21)
    return Detection(image, (image - image.mean(0))*.3, side, .9, 0, origin, detail)


def frame(i, hands, quality=True):
    record = {"frame_index": i, "timestamp_s": i/30, "source_pts_s": i/30, "hands": hands}
    if quality:
        record["quality"] = {"blur_laplacian_var": 100., "mean_luma": 120.,
                             "masks": {"hand_observed": any(h["observed"] for h in hands)}}
    return record


@pytest.fixture(scope="module")
def validator():
    return Draft202012Validator(load_schema())


def test_every_tracker_state_validates(validator):
    tracker = IdentityTracker()
    records = [frame(0, tracker.update([det(), det(.8, "Right")], 0.))]
    records.append(frame(1, tracker.update([det(.41)], 1/30)))   # track 2 predicted
    records.append(frame(2, tracker.update([], .5)))              # both lost
    records.append(frame(3, tracker.update([], 1.5)))             # retired
    records.append(frame(4, baseline_records([det()])))
    states = {h["state"] for r in records for h in r["hands"]}
    assert states == {"observed", "predicted", "lost", "retired"}
    for r in records:
        assert list(validator.iter_errors(r)) == [], r["frame_index"]
    observed = records[0]["hands"][0]
    assert observed["anatomical_side"] == "unknown" and observed["confidence"] is None
    assert observed["provenance"]["image_xyz_raw"] == "predicted"


def test_crop_origins_use_schema_enum(validator):
    mapped = map_crop_detection(det(), (0, 270, 810, 1080), 1920, 1080, "tile", "tile_0")
    hands = baseline_records([mapped])
    assert hands[0]["detection_origin"] == "tile" and hands[0]["detection_origin_detail"] == "tile_0"
    assert list(validator.iter_errors(frame(0, hands))) == []
    hands[0]["detection_origin"] = "tile_0"  # pre-0.5 value
    assert list(validator.iter_errors(frame(0, hands)))


def test_schema_enforces_no_3d_for_unobserved_states(validator):
    tracker = IdentityTracker()
    tracker.update([det()], 0.)
    lost = frame(1, tracker.update([], .5))
    assert list(validator.iter_errors(lost)) == []
    lost["hands"][0]["world_xyz_m_raw"] = [[0., 0., 0.]]*21
    assert any("null" in e.message for e in validator.iter_errors(lost))


def make_run(tmp_path, records):
    run = tmp_path/"run"
    run.mkdir()
    (run/"COMPLETE").touch()
    (run/"landmarks.jsonl").write_text("\n".join(json.dumps(r) for r in records)+"\n")
    return run


def test_validate_jsonl_reports_old_records_with_frame_indices(tmp_path):
    tracker = IdentityTracker()
    good = frame(0, tracker.update([det()], 0.))
    old = json.loads(json.dumps(good))
    old["frame_index"] = 1
    for h in old["hands"]:
        del h["anatomical_side"]
    run = make_run(tmp_path, [good, old])
    result = validate_jsonl(run/"landmarks.jsonl")
    assert (result["frames"], result["invalid_frames"], result["valid"]) == (2, 1, False)
    assert result["errors"][0]["location"] == "$.hands[*]" and "anatomical_side" in result["errors"][0]["message"]
    assert result["examples"][0]["frame_index"] == 1


def test_identity_jsonl_fills_anatomical_side_without_touching_original(tmp_path):
    tracker = IdentityTracker()
    records = [frame(i, tracker.update([det(.3, "Left"), det(.8, "Right")], i/30)) for i in range(5)]
    run = make_run(tmp_path, records)
    original = (run/"landmarks.jsonl").read_text()
    out = write_identity_jsonl(run)
    assert (run/"landmarks.jsonl").read_text() == original
    sides = {h["track_id"]: h["anatomical_side"] for h in json.loads(out.read_text().splitlines()[-1])["hands"]}
    assert sides == {1: "wearer_left", 2: "wearer_right"}
    assert validate_jsonl(out)["valid"]
    with pytest.raises(ValueError, match="never overwritten"):
        write_identity_jsonl(run)
