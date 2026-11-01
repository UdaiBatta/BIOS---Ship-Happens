import json
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
import numpy as np

spec = importlib.util.spec_from_file_location("evaluate_common_clips",
    Path(__file__).parents[1] / "scripts" / "evaluate_common_clips.py")
common = importlib.util.module_from_spec(spec)
spec.loader.exec_module(common)
summarize_run, video_paths = common.summarize_run, common.video_paths


def _hand(track, side, *, observed=True, state="observed", points=True):
    return {"track_id": track, "side": side, "observed": observed, "state": state,
            "image_xyz": [[0, 0, 0]] if points else None}


def test_video_paths_are_recursive_deduplicated_and_sorted(tmp_path):
    folder = tmp_path / "clips"
    folder.mkdir()
    a = folder / "a.MP4"
    b = folder / "sub" / "b.mov"
    b.parent.mkdir()
    a.touch()
    b.touch()

    assert video_paths([folder, a]) == [a.resolve(), b.resolve()]


def test_summary_uses_observed_artifacts_and_ignores_unknown_side_transitions(tmp_path):
    rows = [
        {"frame_index": 0, "hands": [_hand(1, "Left"), _hand(2, None, observed=False, state="predicted")]},
        {"frame_index": 1, "hands": [_hand(1, "unknown"), _hand(2, "Left")]},
        {"frame_index": 2, "hands": [_hand(1, "Right"), _hand(2, "Right")]},
    ]
    (tmp_path / "landmarks.jsonl").write_text("\n".join(json.dumps(x) for x in rows) + "\n")
    (tmp_path / "metrics.json").write_text(json.dumps({"processed_frames": 3,
        "processing_seconds": 2.0, "end_to_end_fps": 1.5}))

    result = summarize_run(tmp_path)

    assert result["observed_hand_frames"] == 3
    assert result["observed_hands"] == 5
    assert result["observed_hands_per_frame"] == pytest.approx(5 / 3)
    assert result["observed_side_counts"] == {"Left": 2, "Right": 2, "unknown": 1}
    assert result["left_right_flips_inside_tracks"] == 1
    assert result["flip_transition_denominator"] == 1
    assert result["predicted_2d_share_denominator"] == 6
    assert result["predicted_2d_hands"] == 1
    assert result["camera_space_lifted_share"] == "not measured"
    assert result["processing_seconds"] == 2.0
    assert result["end_to_end_fps"] == 1.5


def test_summary_rejects_mismatch_with_metrics(tmp_path):
    (tmp_path / "landmarks.jsonl").write_text(json.dumps({"frame_index": 0, "hands": []}) + "\n")
    (tmp_path / "metrics.json").write_text(json.dumps({"processed_frames": 2}))

    with pytest.raises(ValueError, match="frame count"):
        summarize_run(tmp_path)


def test_default_interval_uses_whole_short_clips_and_fixed_long_window():
    assert common.selected_interval(120, None, None)["duration_seconds"] == 120
    long = common.selected_interval(181, None, None)
    assert (long["start_seconds"], long["end_seconds"]) == (0, 30)
    assert common.selected_interval(180.032, None, None)["duration_seconds"] == 30
    assert common.selected_interval(181, 20, 40)["end_seconds"] == 60
    with pytest.raises(ValueError, match="supplied together"):
        common.selected_interval(181, 0, None)
    with pytest.raises(SystemExit):
        common.main(["missing-folder", "--workers", "0"])
    for value in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(ValueError, match="finite"):
            common.selected_interval(181, value, 30)
        with pytest.raises(ValueError, match="finite"):
            common.selected_interval(181, 0, value)
        with pytest.raises(ValueError, match="finite"):
            common.selected_interval(value, None, None)


def _metrics():
    return {"processed_frames": 4, "observed_hand_frames": 3,
            "observed_hand_frames_denominator": 4, "observed_hands": 4,
            "observed_hands_denominator_for_hands_per_frame": 4, "observed_hands_per_frame": 1.,
            "observed_side_counts": {"Left": 1, "Right": 2, "unknown": 1},
            "observed_side_counts_denominator": 4, "left_right_flips_inside_tracks": 1,
            "flip_transition_denominator": 2, "predicted_2d_hands": 1,
            "predicted_2d_share_denominator": 4, "predicted_2d_share": .25,
            "camera_space_lifted_share": "not measured", "processing_seconds": 2.,
            "end_to_end_fps": 2.}


def test_report_has_per_clip_and_pooled_denominators_without_private_metadata():
    summary = {"status": "complete", "requested_clips": 1, "presets": ["baseline"],
               "clips": [{"clip_id": "C1", "source_sha256": "privatehash",
                          "source_path": "private/name.mp4",
                          "selected_interval": {"start_seconds": 0, "end_seconds": 20},
                          "runs": {"baseline": {"status": "complete", "metrics": _metrics()}}}]}

    text = common.report_text(summary)

    assert "Pooled by preset" in text
    assert "### C1 — selected interval: 0–20 s" in text
    assert "| Preset | Status | Observed frames / frames |" in text
    assert "3/4 = 0.750" in text
    assert "1/2 = 0.500" in text
    assert "not measured" in text
    assert "privatehash" not in text and "private/name.mp4" not in text


def test_lift_sidecar_must_match_run_observed_frame_track_pairs(tmp_path, monkeypatch):
    run = tmp_path / "run"
    run.mkdir()
    (run / "landmarks.jsonl").write_text(json.dumps({"frame_index": 3, "hands": [_hand(5, "Left")]}) + "\n")
    np.savez_compressed(run / "lift_hfov150.npz", frame_index=np.array([3]),
                        track_id=np.array([5]), ok=np.array([True]))
    monkeypatch.setattr(common.subprocess, "run", lambda *args, **kwargs:
                        SimpleNamespace(returncode=0, stdout="", stderr=""))

    assert common.measure_camera_lift(run)["share"] == 1.0
    np.savez_compressed(run / "lift_hfov150.npz", frame_index=np.array([4]),
                        track_id=np.array([5]), ok=np.array([True]))
    assert common.measure_camera_lift(run)["status"] == "not measured"


def test_failed_run_writes_private_logs_and_partial_report(tmp_path, monkeypatch):
    clips = [tmp_path / "one.mp4", tmp_path / "two.mp4"]
    for clip in clips:
        clip.touch()
    calls = 0

    monkeypatch.setattr(common, "hybrid_available", lambda repo: False)
    monkeypatch.setattr(common, "hybrid_unavailable_reason", lambda repo: "broken runtime")
    monkeypatch.setattr(common, "probe_duration", lambda clip: 100.)
    monkeypatch.setattr(common, "summarize_run", lambda run: _metrics())
    monkeypatch.setattr(common, "measure_camera_lift", lambda run: {"status": "not measured", "reason": "test"})

    def fake_run(command, **kwargs):
        nonlocal calls
        calls += 1
        return SimpleNamespace(returncode=0 if calls == 1 else 3,
                               stdout="private stdout", stderr="private stderr")

    monkeypatch.setattr(common.subprocess, "run", fake_run)
    out, report = tmp_path / "private-runs", tmp_path / "public-report.md"
    result = common.main([str(tmp_path), "--presets", "baseline", "hybrid", "--out", str(out), "--report", str(report)])

    data = json.loads((out / "summary.json").read_text())
    assert result == 3 and data["status"] == "partial"
    assert data["clips"][0]["runs"]["baseline"]["status"] == "complete"
    assert data["clips"][0]["runs"]["hybrid"]["status"] == "skipped"
    assert data["clips"][0]["runs"]["hybrid"]["reason"] == "broken runtime"
    assert data["clips"][1]["runs"]["baseline"]["status"] == "failed"
    assert "private stdout" in (out / "C2" / "baseline" / "stdout.log").read_text()
    text = report.read_text()
    assert "partial" in text and "process exited with code 3" in text
    assert "one.mp4" not in text and "two.mp4" not in text
