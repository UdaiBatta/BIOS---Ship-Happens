"""Identity metrics for one or more runs: left/right accuracy, label flips, ghosts, same-side pairs.

Usage:  uv run python scripts/evaluate_identity.py LABELS.json RUN:SPLIT [RUN:SPLIT ...]

- side correct: the tracker's shown side vs the labelled wearer side, on labelled hands that
  an observed wrist matches (0.10 image diagonals, as in `egohand evaluate`);
- labelled flips: side changes between consecutive labelled samples of one labelled hand,
  split into "inside one track" and "at a track change";
- side changes within tracks: every change of a track's shown side over the whole run
  (labelled or not) - the flicker a viewer sees;
- ghost frames: a predicted (unobserved) skeleton drawn over an observed hand (>50% box overlap);
- same-side pairs: frames with two observed hands that both carry the same side (Left or Right);
- side unknown: matched hands whose track has no side evidence yet (counted as not correct).
Labels stay private (data/private/); this script only reads them.
"""
from __future__ import annotations

import collections
import json
import sys

import numpy as np

DIAG = np.array([16, 9])/np.hypot(16, 9)


def _box(points):
    a = np.asarray(points)[:, :2]
    return (*a.min(0), *a.max(0))


def _overlap(a, b):
    ix = max(0., min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0., min(a[3], b[3]) - max(a[1], b[1]))
    s = min((a[2] - a[0])*(a[3] - a[1]), (b[2] - b[0])*(b[3] - b[1]))
    return ix*iy/s if s > 0 else 0.


def identity_metrics(run: str, labels: dict, split: str | None) -> dict:
    frames = {}
    with open(f"{run}/landmarks.jsonl") as f:
        for line in f:
            r = json.loads(line)
            frames[r["frame_index"]] = r
    ok = n = unknown = 0
    seq = collections.defaultdict(list)
    for lf in sorted((x for x in labels["frames"] if split is None or x.get("split") == split),
                     key=lambda x: x["frame_index"]):
        obs = [h for h in frames.get(lf["frame_index"], {"hands": []})["hands"] if h["observed"]]
        for g in lf["hands"]:
            if g["side"] not in ("wearer_left", "wearer_right") or not obs:
                continue
            d = [np.linalg.norm((np.array(h["image_xyz_raw"][0][:2]) - g["wrist_xy"])*DIAG) for h in obs]
            if min(d) > .1:
                continue
            h = obs[int(np.argmin(d))]
            truth = "Right" if g["side"] == "wearer_right" else "Left"
            n += 1
            ok += h["side"] == truth
            unknown += h["side"] not in ("Left", "Right")
            seq[g["gt_id"]].append((h["track_id"], h["side"]))
    pairs = [(a, b) for s in seq.values() for a, b in zip(s, s[1:])]
    last, churn, ghosts, two, same = {}, 0, 0, 0, 0
    for idx in sorted(frames):
        hands = frames[idx]["hands"]
        obs = [h for h in hands if h["observed"]]
        for h in obs:
            churn += h["track_id"] in last and last[h["track_id"]] != h["side"]
            last[h["track_id"]] = h["side"]
        pred = [h for h in hands if h["state"] == "predicted" and h.get("image_xyz")]
        ghosts += any(_overlap(_box(p["image_xyz"]), _box(o["image_xyz"])) > .5 for p in pred for o in obs)
        if len(obs) == 2:
            two += 1
            same += obs[0]["side"] == obs[1]["side"] and obs[0]["side"] in ("Left", "Right")
    motion = motion_metrics(frames)
    return {"run": run, "split": split, "side_correct": ok, "side_unknown": unknown, "side_matched": n, **motion,
            "labelled_flips": sum(a[1] != b[1] for a, b in pairs),
            "labelled_flips_inside_track": sum(a[1] != b[1] and a[0] == b[0] for a, b in pairs),
            "side_changes_within_tracks": churn, "ghost_frames": ghosts,
            "two_hand_frames": two, "same_side_two_hand_frames": same}


def motion_metrics(frames: dict) -> dict:
    """Wrist jitter (mean |second difference| over 3 consecutive observed frames of one track, in
    image widths), raw vs smoothed, and the mean smoothed-vs-raw gap when the raw wrist moves faster
    than 0.5 widths/s (lag proxy). Raw values come from image_xyz_raw, smoothed from image_xyz."""
    tracks = collections.defaultdict(list)
    for idx in sorted(frames):
        f = frames[idx]
        for h in f["hands"]:
            if h["observed"] and h.get("image_xyz"):
                tracks[h["track_id"]].append((f["timestamp_s"], np.array(h["image_xyz_raw"][0][:2]),
                                              np.array(h["image_xyz"][0][:2])))
    jr, js, gaps = [], [], []
    for samples in tracks.values():
        for a, b, c in zip(samples, samples[1:], samples[2:]):
            if c[0] - a[0] > .1:                       # only 3 consecutive frames (no gaps)
                continue
            jr.append(np.linalg.norm(a[1] - 2*b[1] + c[1]))
            js.append(np.linalg.norm(a[2] - 2*b[2] + c[2]))
        for a, b in zip(samples, samples[1:]):
            if 0 < b[0] - a[0] < .1 and np.linalg.norm(b[1] - a[1])/(b[0] - a[0]) > .5:
                gaps.append(np.linalg.norm(b[2] - b[1]))
    return {"wrist_jitter_raw": round(float(np.mean(jr)), 5) if jr else None,
            "wrist_jitter_smoothed": round(float(np.mean(js)), 5) if js else None,
            "fast_motion_smoothed_minus_raw": round(float(np.mean(gaps)), 4) if gaps else None,
            "fast_motion_samples": len(gaps)}


def main(argv):
    labels = json.load(open(argv[0]))
    for spec in argv[1:]:
        run, _, split = spec.partition(":")
        print(json.dumps(identity_metrics(run, labels, split or None)))


if __name__ == "__main__":
    main(sys.argv[1:])
