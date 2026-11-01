"""Candidate motion events: evidence-linked, inferred, from tracking states and wrist speed."""
import json

import numpy as np

from egohand_twin.motion_events import derive_events


def _write_run(tmp_path, frames):
    (tmp_path/"manifest.json").write_text(json.dumps({"source": {"width": 1600, "height": 900}}))
    with (tmp_path/"landmarks.jsonl").open("w") as f:
        for i, hands in enumerate(frames):
            f.write(json.dumps({"frame_index": i, "timestamp_s": i/30, "hands": hands}) + "\n")


def _hand(x, state="observed", side="Right"):
    image = np.zeros((21, 3)); image[:, 0] = x; image[:, 1] = .5
    observed = state in ("observed", "reacquired")
    return {"track_id": 1, "state": state, "observed": observed, "side": side,
            "image_xyz": image.tolist() if observed else None, "missing_reason": None if observed else "out_of_view"}


def test_hold_movement_entry_exit_and_gap(tmp_path):
    frames = [[_hand(.3)] for _ in range(45)]                                   # 1.5 s still -> hold
    frames += [[_hand(.3 + .02*i)] for i in range(1, 16)]                       # 0.5 s fast -> movement
    frames += [[_hand(.6, state="lost")] for _ in range(40)]                    # 1.33 s unseen
    frames += [[_hand(.6, state="reacquired")]] + [[_hand(.6)] for _ in range(3)]
    frames += [[_hand(.6, state="lost")]]
    _write_run(tmp_path, frames)
    events = derive_events(tmp_path)["events"]
    kinds = [e["event_type"] for e in events]
    for k in ("hand_entry", "candidate_hold", "candidate_movement", "long_gap", "hand_exit"):
        assert k in kinds, kinds
    hold = next(e for e in events if e["event_type"] == "candidate_hold")
    assert hold["status"] == "inferred" and hold["review_status"] == "unreviewed" and hold["hand"] == "right"
    assert hold["end_time_s"] - hold["start_time_s"] >= 1. and len(hold["evidence_frames"]) == 3
    assert len({e["event_id"] for e in events}) == len(events) and all(len(e["event_id"]) <= 16 for e in events)


def test_unknown_side_is_flagged_not_guessed(tmp_path):
    _write_run(tmp_path, [[_hand(.3, side="unknown")] for _ in range(40)])
    entry = next(e for e in derive_events(tmp_path)["events"] if e["event_type"] == "hand_entry")
    assert entry["hand"] == "unknown" and "side_unknown" in entry["quality_flags"]
