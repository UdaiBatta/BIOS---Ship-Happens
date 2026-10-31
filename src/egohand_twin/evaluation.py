"""Sparse, explicitly labeled evaluation. Predictions never count as detections.

Supports label schema v1 (``identity`` + ``wrist_xy``, reviewed=true) and v2
(split, gt_id, side, visibility, tags, provenance). Unreviewed v2 labels are
rejected unless ``allow_provisional`` is set, in which case every result is
stamped ``label_status="provisional"`` and must not be reported as ground truth.
"""
from __future__ import annotations

from collections import defaultdict
import json
import math
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment

from .conditions import condition_at, load_conditions

WEARER_SIDES = {"wearer_left": "Left", "wearer_right": "Right"}


def wilson(k: int, n: int, z: float = 1.96):
    """95% Wilson score interval; assumes independent samples (optimistic for video)."""
    if n == 0:
        return None
    p = k/n
    centre = (p + z*z/(2*n))/(1 + z*z/n)
    half = z*math.sqrt(p*(1-p)/n + z*z/(4*n*n))/(1 + z*z/n)
    return [round(max(0., centre-half), 4), round(min(1., centre+half), 4)]


def _rate(k, n):
    return {"value": k/n if n else None, "k": k, "n": n, "wilson95": wilson(k, n)}


def load_labels(labels: Path, source_sha256: str, allow_provisional: bool = False) -> dict:
    annotations = json.loads(labels.read_text())
    if annotations.get("source_sha256") != source_sha256:
        raise ValueError("Labels must contain the matching source_sha256 from manifest.json")
    status = "reviewed"
    if annotations.get("reviewed") is not True:
        if not (allow_provisional and str(annotations.get("schema_version", "1")).startswith("2")):
            raise ValueError("Annotations must be manually reviewed and set reviewed=true "
                             "(v2 provisional labels require --allow-provisional)")
        status = "provisional"
    if not annotations.get("frames"):
        raise ValueError("No labeled frames")
    hands_seen = 0
    for frame in annotations["frames"]:
        if frame.get("complete") is False:
            raise ValueError(f"Frame {frame['frame_index']} is not marked complete")
        gt = frame["hands"]
        frame.setdefault("split", "unspecified")
        frame.setdefault("interval", frame["split"])
        for g in gt:
            g.setdefault("gt_id", g.get("identity"))
            if g["gt_id"] is None:
                raise ValueError("Each hand needs gt_id (v2) or identity (v1)")
            g.setdefault("side", "unknown")
            g.setdefault("visibility", "unspecified")
            g.setdefault("tags", [])
            g.setdefault("wrist_in_frame", True)
            wrist = np.asarray(g["wrist_xy"], dtype=float)
            low, high = (0., 1.) if g["wrist_in_frame"] else (-.25, 1.25)
            if wrist.shape != (2,) or not np.isfinite(wrist).all() or np.any((wrist < low) | (wrist > high)):
                raise ValueError("Ground-truth wrist_xy must be finite normalized x,y "
                                 "(outside [0,1] only with wrist_in_frame=false)")
            hands_seen += 1
        if len({g["gt_id"] for g in gt}) != len(gt):
            raise ValueError("Duplicate ground-truth identity within a frame")
    annotations["_status"] = status
    return annotations


def load_predictions(run: Path) -> dict[int, dict]:
    predictions = {}
    with (run/"landmarks.jsonl").open() as f:
        for line in f:
            frame = json.loads(line)
            predictions[frame["frame_index"]] = frame
    return predictions


def _match(gt, pred, scale, threshold):
    if not gt or not pred:
        return [], np.zeros((len(gt), len(pred)))
    cost = np.array([[np.linalg.norm((np.array(g["wrist_xy"]) - np.array(p["image_xyz_raw"])[0, :2])*scale)
                      for p in pred] for g in gt])
    # Gate BEFORE assignment so an invalid edge cannot displace a valid one.
    gated = np.where(cost <= threshold, cost, 1e6)
    rows, cols = linear_sum_assignment(gated)
    return [(int(r), int(c)) for r, c in zip(rows, cols) if gated[r, c] < 1e6], cost


class _Counter:
    def __init__(self):
        self.tp = self.fn = 0

    def as_dict(self):
        return {"labeled_hands": self.tp+self.fn, "matched": self.tp, "missed": self.fn,
                "recall": _rate(self.tp, self.tp+self.fn)}


def continuity(samples) -> dict:
    """Run-level continuity from (timestamp_s, hand_record) pairs in time order. No labels needed.

    - predicted runs: consecutive ``predicted`` samples of a track (2D-only, capped at
      ~0.15 s by the tracker; reported as a check of that rule).
    - bridged gaps: unobserved time between two observed samples of the same track
      (the track was reacquired), i.e. last observed -> next observed timestamp.
    - terminal gaps: tracks whose last state is not observed (ended lost/retired).
    Seconds use source presentation time. These are tracker statistics, not accuracy.
    """
    tracks: dict[int, list] = {}
    for t, hand in samples:
        tracks.setdefault(hand["track_id"], []).append((t, hand["state"], hand["observed"]))
    predicted_runs, bridged, observed_counts = [], [], []
    terminal = 0
    for rows in tracks.values():
        run_start = last_obs = None
        observed_counts.append(sum(o for _, _, o in rows))
        for i, (t, state, observed) in enumerate(rows):
            if state == "predicted":
                run_start = t if run_start is None else run_start
                nxt = rows[i+1][0] if i+1 < len(rows) else t
                if i+1 == len(rows) or rows[i+1][1] != "predicted":
                    predicted_runs.append(nxt - run_start if i+1 < len(rows) else t - run_start)
                    run_start = None
            if observed:
                if last_obs is not None and t - last_obs[0] > 0 and last_obs[1] != i - 1:
                    bridged.append(t - last_obs[0])
                last_obs = (t, i)
        if rows and not rows[-1][2]:
            terminal += 1

    def stats(values):
        return ({"n": len(values), "median_s": float(np.median(values)), "max_s": float(np.max(values))}
                if values else {"n": 0})
    return {"tracks": len(tracks), "observed_samples_per_track_median":
            float(np.median(observed_counts)) if observed_counts else None,
            "predicted_runs": stats(predicted_runs), "bridged_gaps": stats(bridged),
            "tracks_ending_unobserved": terminal,
            "note": "Tracker statistics from the run itself; not compared with labels."}


def evaluate(run: Path, labels: Path, wrist_threshold=.10, pck_threshold=.03,
             allow_provisional=False, audit_thresholds=(.05, .10), split=None, conditions=None):
    if not (run/"COMPLETE").exists():
        raise ValueError("Run is incomplete")
    split_filter = split
    manifest = json.loads((run/"manifest.json").read_text())
    annotations = load_labels(labels, manifest["source"]["sha256"], allow_provisional)
    intervals = load_conditions(conditions, manifest["source"]["sha256"]) if conditions else None
    excluded = {"frames": 0, "labeled_hands": 0, "reasons": {}}
    if split is not None:
        annotations["frames"] = [f for f in annotations["frames"] if f["split"] == split]
        if not annotations["frames"]:
            raise ValueError(f"No labeled frames in split {split!r}")
    predictions = load_predictions(run)
    votes = None
    if (run/"identity.json").exists():
        votes = json.loads((run/"identity.json").read_text())["tracks"]
    w, h = manifest["source"]["width"], manifest["source"]["height"]
    scale = np.array([w, h])/np.hypot(w, h)
    tp = fp = fn = switches = points_correct = points_total = 0
    distances, match_distances = [], []
    previous_ids = {}
    seen_frames = set()
    groups: dict[str, _Counter] = defaultdict(_Counter)
    split_fp: dict[str, int] = defaultdict(int)
    split_pred: dict[str, int] = defaultdict(int)
    false_positive_frames, missed = [], []
    side_raw = defaultdict(int)
    side_track = defaultdict(int)
    side_vote = defaultdict(int)
    origin_counts = defaultdict(lambda: [0, 0])
    audit = {t: [0, 0] for t in audit_thresholds}
    frames_with_gt = frames_with_gt_and_pred = 0
    id_history: list = []
    # Last observed wrist per track (scanning every processed frame in order), used to
    # check missing_reason claims against labeled hands that were not detected.
    last_wrist: dict[int, dict[int, np.ndarray]] = {}
    current: dict[int, np.ndarray] = {}
    for index in sorted(predictions):
        last_wrist[index] = dict(current)
        for p in predictions[index]["hands"]:
            if p["observed"]:
                current[p["track_id"]] = np.array(p["image_xyz_raw"][0][:2])
    reason_check = {"out_of_view": [0, 0], "unknown": [0, 0]}
    nearby = .15
    id_pairs = id_changes = 0
    for frame in sorted(annotations["frames"], key=lambda x: x["frame_index"]):
        index = frame["frame_index"]
        if index in seen_frames:
            raise ValueError("Duplicate annotated frame")
        seen_frames.add(index)
        if index not in predictions:
            raise ValueError(f"Annotated frame {index} was not processed")
        condition = condition_at(intervals, predictions[index]["timestamp_s"]) if intervals else None
        if condition and condition["excluded"]:
            # Excluded frames are reported, never silently dropped.
            excluded["frames"] += 1
            excluded["labeled_hands"] += len(frame["hands"])
            reason = condition["exclusion_reason"]
            excluded["reasons"][reason] = excluded["reasons"].get(reason, 0) + 1
            continue
        gt = frame["hands"]  # Must list ALL visible, labelable hands in this frame.
        pred = [p for p in predictions[index]["hands"] if p["observed"]]
        split = frame["split"]
        matches, cost = _match(gt, pred, scale, wrist_threshold)
        for t in audit_thresholds:
            m, _ = _match(gt, pred, scale, t)
            audit[t][0] += len(m)
            audit[t][1] += len(pred) - len(m)
        unmatched_gt = [g for r, g in enumerate(gt) if r not in {m[0] for m in matches}]
        for p in predictions[index]["hands"]:
            reason = p.get("missing_reason")
            if p["observed"] or reason not in reason_check or p["track_id"] not in last_wrist[index]:
                continue
            wrist = last_wrist[index][p["track_id"]]
            close = any(np.linalg.norm((np.array(g["wrist_xy"]) - wrist)*scale) <= nearby for g in unmatched_gt)
            reason_check[reason][0] += 1
            reason_check[reason][1] += bool(close)
        frames_with_gt += bool(gt)
        frames_with_gt_and_pred += bool(gt) and bool(pred)
        tp += len(matches)
        fn += len(gt)-len(matches)
        fp += len(pred)-len(matches)
        split_fp[split] += len(pred)-len(matches)
        split_pred[split] += len(pred)
        matched_gt = {r: c for r, c in matches}
        matched_pred = {c for _, c in matches}
        for c, p in enumerate(pred):
            origin = p.get("detection_origin") or "full_frame"
            origin_counts[origin][0 if c in matched_pred else 1] += 1
            if c not in matched_pred:
                false_positive_frames.append({"frame_index": index, "split": split,
                                              "wrist_xy": [round(v, 4) for v in p["image_xyz_raw"][0][:2]],
                                              "origin": origin})
        for r, g in enumerate(gt):
            keys = ["all", f"split={split}", f"visibility={g['visibility']}",
                    f"split={split}|visibility={g['visibility']}", f"side={g['side']}"]
            keys += [f"tag={t}" for t in g["tags"]]
            if intervals is not None:
                for k in ("glove_ppe", "occlusion", "lighting"):
                    keys.append(f"condition.{k}={condition[k] if condition else 'not_annotated'}")
            for key in keys:
                counter = groups[key]
                if r in matched_gt:
                    counter.tp += 1
                else:
                    counter.fn += 1
            if r not in matched_gt:
                missed.append({"frame_index": index, "split": split, "gt_id": g["gt_id"],
                               "visibility": g["visibility"], "tags": g["tags"]})
        for r, c in matches:
            g, p = gt[r], pred[c]
            match_distances.append(float(cost[r, c]))
            expected = WEARER_SIDES.get(g["side"])
            if expected:
                side_raw[(split, g["side"], p.get("raw_side"))] += 1
                side_track[(split, g["side"], p.get("side"))] += 1
                if votes is not None:
                    side_vote[(split, g["side"], votes.get(str(p["track_id"]), {}).get("side_vote", "unknown"))] += 1
            key = (frame["interval"], g["gt_id"])
            id_history.append((key, p["track_id"]))
            if key in previous_ids:
                id_pairs += 1
                if previous_ids[key] != p["track_id"]:
                    id_changes += 1
            previous_ids[key] = p["track_id"]
            if "landmarks_xy" in g and g["landmarks_xy"] is not None:
                landmarks = g["landmarks_xy"]
                if len(landmarks) != 21:
                    raise ValueError("landmarks_xy must have 21 entries; use null for unlabeled joints")
                for j, xy in enumerate(landmarks):
                    if xy is None:
                        continue
                    xy = np.asarray(xy, dtype=float)
                    if xy.shape != (2,) or not np.isfinite(xy).all():
                        raise ValueError("Invalid landmark annotation")
                    distance = float(np.linalg.norm((xy-np.array(p["image_xyz_raw"])[j, :2])*scale))
                    distances.append(distance)
                    points_total += 1
                    points_correct += distance <= pck_threshold
    switches = id_changes
    fragments: dict[tuple, set] = {}
    for key, tid in id_history:
        fragments.setdefault(key, set()).add(tid)
    complete = all("timestamp_s" in f and all("state" in h for h in f["hands"]) for f in predictions.values())
    run_continuity = (continuity((predictions[i]["timestamp_s"], h) for i in sorted(predictions)
                                 for h in predictions[i]["hands"])
                      if complete else {"unavailable": "run records lack timestamp_s/state"})

    def side_summary(table):
        out = {}
        for split in sorted({k[0] for k in table} | {"all"}):
            rows = {k: v for k, v in table.items() if split == "all" or k[0] == split}
            correct = sum(v for (s, g, p), v in rows.items() if WEARER_SIDES[g] == p)
            mirrored = sum(v for (s, g, p), v in rows.items()
                           if p in ("Left", "Right") and WEARER_SIDES[g] != p)
            n = sum(rows.values())
            confusion = defaultdict(int)
            for (s, g, p), v in rows.items():
                confusion[f"{g}->{p}"] += v
            out[split] = {"accuracy_as_labeled": _rate(correct, n),
                          "accuracy_if_mirrored": _rate(mirrored, n),
                          "confusion": dict(sorted(confusion.items()))}
        return out

    precision_by_split = {s: _rate(split_pred[s]-split_fp[s], split_pred[s]) for s in sorted(split_pred)}
    return {
        "label_status": annotations["_status"],
        "label_schema_version": str(annotations.get("schema_version", "1")),
        "split_filter": split_filter,
        "conditions_file": str(conditions) if conditions else None,
        "excluded_by_conditions": excluded if conditions else None,
        "labeled_frames": len(seen_frames),
        "frames_with_labeled_hands": frames_with_gt,
        "frames_with_labeled_hands_and_observed_prediction": frames_with_gt_and_pred,
        "true_positives": tp, "false_positives": fp, "false_negatives": fn,
        "precision": tp/(tp+fp) if tp+fp else None,
        "recall": tp/(tp+fn) if tp+fn else None,
        "recall_detail": groups["all"].as_dict()["recall"],
        "precision_detail": _rate(tp, tp+fp),
        "precision_by_split": precision_by_split,
        "recall_by_group": {k: v.as_dict() for k, v in sorted(groups.items())},
        "wrist_match_threshold_image_diagonal": wrist_threshold,
        "matched_wrist_distance_image_diagonal": (
            {"median": float(np.median(match_distances)), "p90": float(np.percentile(match_distances, 90)),
             "max": float(np.max(match_distances))} if match_distances else None),
        "threshold_audit": {str(t): {"matched": v[0], "unmatched_predictions": v[1]}
                            for t, v in audit.items()},
        "side_accuracy_raw_per_frame": side_summary(side_raw),
        "side_accuracy_track_smoothed": side_summary(side_track),
        "side_accuracy_offline_track_vote": side_summary(side_vote) if votes is not None else None,
        "detections_by_origin": {k: {"matched": v[0], "unmatched": v[1]} for k, v in sorted(origin_counts.items())},
        "missing_reason_check": {
            "rule": f"a labeled, undetected hand lies within {nearby} image diagonals of the track's last observed wrist",
            "out_of_view": {"claims": reason_check["out_of_view"][0],
                            "contradicted_by_nearby_undetected_hand": reason_check["out_of_view"][1]},
            "unknown": {"records": reason_check["unknown"][0],
                        "with_nearby_undetected_hand": reason_check["unknown"][1]},
            "note": "Only non-observed track records in labeled frames; runs without missing_reason report zeros."},
        "fragments": {
            "labeled_identities_with_matches": len(fragments),
            "track_ids_per_identity": {f"{k[0]}:{k[1]}" if not str(k[1]).startswith(str(k[0])) else str(k[1]):
                                       len(v) for k, v in sorted(fragments.items(), key=lambda x: str(x[0]))},
            "mean_track_ids_per_identity": (float(np.mean([len(v) for v in fragments.values()]))
                                            if fragments else None),
            "note": "Distinct track IDs matched to one labeled hand within one labeled interval (1 = no fragmentation)."},
        "run_continuity": run_continuity,
        "sampled_identity_switches": switches,
        "sampled_identity_pairs": id_pairs,
        "pck_on_matched_hands": points_correct/points_total if points_total else None,
        "pck_threshold_image_diagonal": pck_threshold,
        "labeled_joints_on_matched_hands": points_total,
        "mean_joint_error_image_diagonal": float(np.mean(distances)) if distances else None,
        "false_positive_predictions": false_positive_frames,
        "missed_hands": missed,
        "3d_error": None,
        "limitations": ["Only manually labeled frames are scored; sample bias may be substantial.",
                        "Wilson intervals assume independent samples; adjacent video frames are correlated, so true uncertainty is larger.",
                        "Identity changes are counted between consecutive labeled samples of the same gt_id within one interval, including across unlabeled gaps.",
                        "PCK is conditional on matched detections and excludes missing/unlabeled joints.",
                        "2D annotations do not establish 3D accuracy; no 3D ground truth was provided."]
                       + (["PROVISIONAL LABELS: not independently human-reviewed; do not report as ground truth."]
                          if annotations["_status"] == "provisional" else []),
    }
