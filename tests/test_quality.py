import json

import cv2
import numpy as np

from egohand_twin.model import sha256
from egohand_twin.quality import QualityConfig, assess, evaluate_quality, export_segments, write_quality

FPS = 30


def make_run(tmp_path, observed_fn, n=90):
    """Synthetic textured video + cached run: observed_fn(i) -> list of (track_id, x, y)."""
    video = tmp_path/"clip.avi"
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"MJPG"), FPS, (160, 90))
    rng = np.random.default_rng(0)
    texture = rng.integers(0, 255, (90, 160, 3), np.uint8)
    for i in range(n):
        writer.write(np.roll(texture, i % 3, axis=1))
    writer.release()
    run = tmp_path/"run"
    run.mkdir()
    (run/"COMPLETE").touch()
    (run/"manifest.json").write_text(json.dumps({"source": {"name": "clip.avi", "sha256": sha256(video),
                                                            "width": 160, "height": 90}, "parameters": {}}))
    seen = set()
    lines = []
    for i in range(n):
        hands = []
        present = {tid: (x, y) for tid, x, y in observed_fn(i)}
        for tid, (x, y) in present.items():
            image = np.zeros((21, 3))
            image[:, 0] = x + np.linspace(0, .05, 21)
            image[:, 1] = y - np.linspace(0, .1, 21)
            world = (image-image.mean(0))*.3 + np.linspace(0, .01, 21)[:, None]
            hands.append({"track_id": tid, "state": "observed", "observed": True, "side": "Left",
                          "raw_side": "Left", "handedness_score": .9, "detection_origin": "full_frame",
                          "image_xyz_raw": image.tolist(), "world_xyz_m_raw": world.tolist()})
            seen.add(tid)
        for tid in seen - set(present):
            hands.append({"track_id": tid, "state": "lost", "observed": False, "side": "Left",
                          "image_xyz_raw": None, "world_xyz_m_raw": None})
        lines.append(json.dumps({"frame_index": i, "timestamp_s": i/FPS, "hands": hands}))
    (run/"landmarks.jsonl").write_text("\n".join(lines)+"\n")
    return run, video


def test_statuses_queue_and_provenance(tmp_path):
    # 0-1 s steady hand; 1-2 s flickering hand (gaps); 2-3 s nothing observed.
    def observed(i):
        if i < 30:
            return [(1, .4, .6)]
        if i < 60:
            return [(1, .4, .6)] if i % 10 < 3 else []
        return []
    run, video = make_run(tmp_path, observed)
    r = assess(run, video, QualityConfig())
    statuses = [w["status"] for w in r["windows"]]
    assert statuses == ["suitable", "needs_review", "insufficient_evidence"]
    assert "low_coverage" in r["windows"][1]["reasons"]
    assert r["windows"][2]["reasons"][0] == "no_observed_hand"
    item = [q for q in r["queue"] if q["status"] == "needs_review"][0]
    assert item["assessment_source"] == "heuristic" and item["first_frame"] == 30 and item["last_frame"] == 59
    assert item["track_ids"] == [1] and item["suggested_actions"]
    summary = write_quality(run, video)
    assert summary["review_items"] == 1
    assert (run/"quality"/"review_queue.csv").read_text().count("\n") == 4
    queue = json.loads((run/"quality"/"review_queue.json").read_text())
    assert all(q["source_sha256"] == sha256(video) and q["run_id"] for q in queue)


def test_long_intervals_split_and_jumps_detected(tmp_path):
    def observed(i):
        return [(1, .2 if (i // 15) % 2 else .7, .6)]  # wrist teleports every 0.5 s
    run, video = make_run(tmp_path, observed, n=240)
    r = assess(run, video, QualityConfig(max_item_s=3.))
    assert all(w["status"] == "needs_review" and "landmark_jump" in w["reasons"] for w in r["windows"])
    assert [q["end_s"]-q["start_s"] for q in r["queue"]] == [3., 3., 2.]


def test_mismatched_video_rejected(tmp_path):
    run, video = make_run(tmp_path, lambda i: [])
    other = tmp_path/"other.avi"
    other.write_bytes(video.read_bytes()+b"x")
    try:
        assess(run, other)
    except ValueError as error:
        assert "does not match" in str(error)
    else:
        raise AssertionError("expected mismatch error")


def test_segment_export_copies_records_unchanged(tmp_path):
    run, video = make_run(tmp_path, lambda i: [(1, .4, .6)] if i < 30 else [])
    write_quality(run, video)
    manifest = export_segments(run, tmp_path/"export", "suitable")
    assert len(manifest["segments"]) == 1 and manifest["segments"][0]["observed_hand_records"] == 30
    exported = (tmp_path/"export"/manifest["segments"][0]["file"]).read_text().splitlines()
    original = (run/"landmarks.jsonl").read_text().splitlines()[:30]
    assert [json.loads(a) for a in exported] == [json.loads(b) for b in original]


def test_quality_flags_scored_against_labeled_frames(tmp_path):
    windows = [{"start_s": 0., "end_s": 1., "status": "suitable"},
               {"start_s": 1., "end_s": 2., "status": "needs_review"},
               {"start_s": 2., "end_s": 3., "status": "insufficient_evidence"}]
    labels = tmp_path/"labels.json"
    labels.write_text(json.dumps({"frames": [
        {"frame_index": 0, "timestamp_s": .5, "split": "dev", "hands": [{"gt_id": "a"}]},
        {"frame_index": 45, "timestamp_s": 1.5, "split": "dev", "hands": [{"gt_id": "a"}]},
        {"frame_index": 75, "timestamp_s": 2.5, "split": "dev", "hands": [{"gt_id": "a"}]},
        {"frame_index": 80, "timestamp_s": 2.7, "split": "dev", "hands": []}]}))
    evaluation = {"label_status": "provisional", "missed_hands": [{"frame_index": 45}, {"frame_index": 75}]}
    q = evaluate_quality(windows, labels, evaluation, "dev")
    assert q["missed_frames_in_flagged_windows"] == {"k": 2, "n": 2}
    assert q["all_matched_frames_in_suitable_windows"] == {"k": 1, "n": 1}
    assert q["insufficient_evidence_frames_with_visible_hand"] == {"k": 1, "n": 2}
