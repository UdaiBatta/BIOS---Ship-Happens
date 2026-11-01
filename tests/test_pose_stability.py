import copy
import importlib.util
import json
from pathlib import Path

import pytest


spec = importlib.util.spec_from_file_location("compare_pose_stability", Path(__file__).parents[1]/"scripts"/"compare_pose_stability.py")
stability = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stability)


def runs(tmp_path):
    steady = [[0., i*.01, i*.001] for i in range(21)]
    frames = []
    for i in range(3):
        raw = [[p[1], p[0], p[2]] for p in steady] if i == 1 else copy.deepcopy(steady)
        frames.append({"frame_index": i, "timestamp_s": i/30, "hands": [{"track_id": 1,
            "observed": True, "world_xyz_m_raw": raw, "world_xyz_m": copy.deepcopy(raw),
            "image_xyz_raw": copy.deepcopy(steady)}]})
    candidate = copy.deepcopy(frames)
    for frame in candidate:
        frame["hands"][0]["world_xyz_m"] = copy.deepcopy(steady)
    paths = [tmp_path/"old", tmp_path/"new"]
    for path, data in zip(paths, [frames, candidate]):
        path.mkdir()
        (path/"landmarks.jsonl").write_text("".join(json.dumps(f)+"\n" for f in data))
    return paths, candidate


def test_stability_comparison_uses_identical_raw_data_and_tracks(tmp_path):
    paths, _ = runs(tmp_path)
    result = stability.compare(*paths)
    assert result["identical_raw_samples"] == 3
    assert result["consecutive_hand_triples"] == 1
    assert result["before"]["finger_bone_samples"] == result["after"]["finger_bone_samples"] == 16
    assert result["before"]["p90"] > 0 and result["after"]["p90"] == 0
    assert result["p90_reduction_percent"] == pytest.approx(100)


def test_stability_comparison_rejects_changed_raw_observations(tmp_path):
    paths, candidate = runs(tmp_path)
    candidate[1]["hands"][0]["world_xyz_m_raw"][5][0] += .1
    (paths[1]/"landmarks.jsonl").write_text("".join(json.dumps(f)+"\n" for f in candidate))
    with pytest.raises(ValueError, match="Raw observations differ"):
        stability.compare(*paths)
