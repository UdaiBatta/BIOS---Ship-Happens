"""Offline whole-track left/right estimate, kept separate from per-frame outputs.

MediaPipe's per-frame handedness is noisy on back-of-hand, blurred and cloth-covered
views. Because a short-term track is (by construction) one physical hand, a vote
over all of its *observed* frames can be steadier than the online running average.

This is a post-processing view: raw per-frame ``raw_side``/``handedness_score`` and
the online ``side`` remain unchanged in ``landmarks.jsonl``. Tracks with too little
evidence or an ambiguous vote are labelled ``unknown`` rather than forced to a side,
and two simultaneous tracks are never forced to be one left and one right. Wrong
track associations (ID switches) propagate into the vote; the vote cannot repair them.
"""
from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path


def right_probability(hand: dict) -> float:
    score = hand["handedness_score"]
    return score if hand["raw_side"] == "Right" else 1. - score


def track_votes(run: Path, margin: float = .15, min_observed: int = 3) -> dict:
    stats = defaultdict(lambda: {"n": 0, "sum": 0., "first_s": None, "last_s": None})
    with (run/"landmarks.jsonl").open() as f:
        for line in f:
            frame = json.loads(line)
            for hand in frame["hands"]:
                if not hand["observed"]:
                    continue
                s = stats[hand["track_id"]]
                s["n"] += 1
                s["sum"] += right_probability(hand)
                s["first_s"] = frame["timestamp_s"] if s["first_s"] is None else s["first_s"]
                s["last_s"] = frame["timestamp_s"]
    tracks = {}
    for track_id, s in sorted(stats.items()):
        p = s["sum"]/s["n"]
        if s["n"] < min_observed or abs(p-.5) < margin:
            side = "unknown"
        else:
            side = "Right" if p > .5 else "Left"
        tracks[str(track_id)] = {"side_vote": side, "mean_p_right": round(p, 4),
                                 "observed_frames": s["n"], "first_s": s["first_s"], "last_s": s["last_s"]}
    return {"method": "mean of per-frame right-probability over observed frames of each short-term track",
            "margin": margin, "min_observed": min_observed,
            "note": "Track-level vote; raw per-frame handedness is preserved separately. 'unknown' is not forced.",
            "tracks": tracks}


def write_identity(run: Path, margin: float = .15, min_observed: int = 3) -> Path:
    if not (run/"COMPLETE").exists():
        raise ValueError("Run is incomplete")
    result = track_votes(run, margin, min_observed)
    path = run/"identity.json"
    path.write_text(json.dumps(result, indent=2)+"\n")
    return path


ANATOMICAL = {"Left": "wearer_left", "Right": "wearer_right", "unknown": "unknown"}


def write_identity_jsonl(run: Path, margin: float = .15, min_observed: int = 3) -> Path:
    """Write RUN/landmarks.identity.jsonl: landmarks.jsonl with anatomical_side from the track vote.

    ASSUMPTION: every detected hand belongs to the camera wearer. The vote cannot
    detect other people's hands, so ``other`` is never assigned; a background hand
    would be mislabeled wearer_left/right. On the test clip (provisional labels) the
    vote was correct for 30/38 matched holdout wearer hands, wrong for 5, unknown for 3.
    The original landmarks.jsonl is never modified.
    """
    out = run/"landmarks.identity.jsonl"
    if out.exists():
        raise ValueError("landmarks.identity.jsonl exists; never overwritten")
    votes = track_votes(run, margin, min_observed)["tracks"]
    with (run/"landmarks.jsonl").open() as source, out.open("w") as target:
        for line in source:
            frame = json.loads(line)
            for hand in frame["hands"]:
                vote = votes.get(str(hand["track_id"]), {}).get("side_vote", "unknown")
                hand["anatomical_side"] = ANATOMICAL[vote]
                hand["anatomical_side_basis"] = (
                    f"whole-track vote over observed frames (margin {margin}, min {min_observed}); "
                    "assumes the hand belongs to the wearer")
                hand.setdefault("provenance", {})["anatomical_side"] = "inferred"
            target.write(json.dumps(frame, separators=(",", ":"), allow_nan=False)+"\n")
    return out
