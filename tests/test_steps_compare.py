import json

import cv2
import numpy as np
import pytest

from motioniq.compare import compare, find_frame
from motioniq.model import sha256
from motioniq.steps import load_steps, template, validate_steps, write_template

FPS = 10


def make_run(tmp_path, observed_frames=(2, 3), n=8):
    video = tmp_path/"clip.avi"
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"MJPG"), FPS, (160, 90))
    for i in range(n):
        writer.write(np.full((90, 160, 3), 20*i, np.uint8))
    writer.release()
    run = tmp_path/"run"
    run.mkdir()
    (run/"COMPLETE").touch()
    (run/"manifest.json").write_text(json.dumps({"source": {"name": "clip.avi", "sha256": sha256(video),
                                                            "width": 160, "height": 90}}))
    lines = []
    for i in range(n):
        hands = []
        if i in observed_frames:
            image = np.zeros((21, 3))
            image[:, 0] = .4 + np.linspace(0, .1, 21)
            image[:, 1] = .7 - np.linspace(0, .3, 21)
            world = np.zeros((21, 3))
            world[:, 1] = -np.linspace(0, .08, 21)
            hands.append({"track_id": 1, "state": "observed", "observed": True, "side": "Left",
                          "side_probability_right_smoothed": .1, "detection_origin": "full_frame",
                          "image_xyz": image.tolist(), "image_xyz_raw": image.tolist(),
                          "world_xyz_m_raw": world.tolist()})
        elif i > max(observed_frames):
            hands.append({"track_id": 1, "state": "lost", "observed": False, "side": "Left",
                          "image_xyz": None, "image_xyz_raw": None, "world_xyz_m_raw": None})
        lines.append(json.dumps({"frame_index": i, "timestamp_s": i/FPS, "source_pts_s": i/FPS, "hands": hands}))
    (run/"landmarks.jsonl").write_text("\n".join(lines)+"\n")
    return run, video


def good_steps(run, **override):
    data = template(run)
    step = {"start_s": .1, "end_s": .5, "label": "Wipe slab", "version": 1, "note": "",
            "reviewer": None, "signed_off": False}
    step.update(override)
    data["steps"] = [step]
    return data


def test_steps_template_and_valid_sidecar(tmp_path):
    run, _ = make_run(tmp_path)
    path = write_template(run, tmp_path/"steps.json")
    assert json.loads(path.read_text())["steps"] == []
    with pytest.raises(ValueError, match="never overwritten"):
        write_template(run, path)
    data = good_steps(run)
    data["steps"].insert(0, {**data["steps"][0], "start_s": 0., "end_s": .2, "label": "Pick cloth"})
    steps = validate_steps(data, run)
    assert [s["label"] for s in steps] == ["Pick cloth", "Wipe slab"]
    path2 = tmp_path/"s2.json"
    path2.write_text(json.dumps(data))
    assert len(load_steps(path2, run)) == 2


@pytest.mark.parametrize("override,message", [
    ({"start_s": .5, "end_s": .5}, "before end_s"),
    ({"end_s": 9.}, "outside the processed interval"),
    ({"label": "  "}, "label"),
    ({"version": 0}, "version"),
    ({"signed_off": True, "reviewer": ""}, "requires a reviewer"),
    ({"signed_off": "yes"}, "true or false"),
    ({"start_s": float("nan")}, "finite"),
])
def test_invalid_steps_rejected(tmp_path, override, message):
    run, _ = make_run(tmp_path)
    with pytest.raises(ValueError, match=message):
        validate_steps(good_steps(run, **override), run)


def test_steps_bound_to_source_and_run(tmp_path):
    run, _ = make_run(tmp_path)
    data = good_steps(run)
    with pytest.raises(ValueError, match="different processing run"):
        validate_steps({**data, "run_id": "000000000000"}, run)
    with pytest.raises(ValueError, match="different source"):
        validate_steps({**data, "source_sha256": "x"}, run)
    missing = good_steps(run)
    del missing["steps"][0]["reviewer"]
    with pytest.raises(ValueError, match="missing fields"):
        validate_steps(missing, run)


def test_compare_refuses_frames_without_observed_hand(tmp_path):
    run, video = make_run(tmp_path, observed_frames=(2, 3))
    assert find_frame(run, frame_index=3)["frame_index"] == 3
    assert find_frame(run, time_s=.21)["frame_index"] == 2
    with pytest.raises(ValueError, match=r"before \[3\], after \[\]"):
        find_frame(run, frame_index=5)  # lost track: no 3D may be shown
    with pytest.raises(ValueError, match="not processed"):
        find_frame(run, frame_index=99)


def test_compare_writes_image_and_provenance_once(tmp_path):
    run, video = make_run(tmp_path)
    out = tmp_path/"cmp"/"moment.png"
    meta = compare(video, run, out, frame_index=2)
    image = cv2.imread(str(out))
    assert image.shape == (900, 1600, 3)
    assert meta["frame_index"] == 2 and meta["hands"][0]["state"] == "observed"
    assert json.loads(out.with_suffix(".json").read_text())["source_sha256"] == sha256(video)
    with pytest.raises(ValueError, match="never overwritten"):
        compare(video, run, out, frame_index=2)
    other = tmp_path/"other.avi"
    other.write_bytes(video.read_bytes()+b"x")
    with pytest.raises(ValueError, match="does not match"):
        compare(other, run, tmp_path/"x.png", frame_index=2)
