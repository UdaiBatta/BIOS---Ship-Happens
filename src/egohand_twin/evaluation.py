"""Sparse, explicitly labeled evaluation. Predictions never count as detections."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment


def evaluate(run: Path, labels: Path, wrist_threshold=.10, pck_threshold=.03):
    if not (run/"COMPLETE").exists():
        raise ValueError("Run is incomplete")
    manifest = json.loads((run/"manifest.json").read_text())
    annotations = json.loads(labels.read_text())
    if annotations.get("source_sha256") != manifest["source"]["sha256"]:
        raise ValueError("Labels must contain the matching source_sha256 from manifest.json")
    if annotations.get("reviewed") is not True:
        raise ValueError("Annotations must be manually reviewed and set reviewed=true")
    if not annotations.get("frames"):
        raise ValueError("No labeled frames")
    predictions = {}
    with (run/"landmarks.jsonl").open() as f:
        for line in f:
            frame = json.loads(line)
            predictions[frame["frame_index"]] = frame
    w, h = manifest["source"]["width"], manifest["source"]["height"]
    scale = np.array([w, h])/np.hypot(w, h)
    tp = fp = fn = switches = points_correct = points_total = 0
    distances = []
    previous_ids = {}
    seen_frames = set()
    for frame in sorted(annotations["frames"], key=lambda x: x["frame_index"]):
        index = frame["frame_index"]
        if index in seen_frames:
            raise ValueError("Duplicate annotated frame")
        seen_frames.add(index)
        if index not in predictions:
            raise ValueError(f"Annotated frame {index} was not processed")
        gt = frame["hands"]  # Must list ALL visible, labelable hands in this frame.
        if len({g["identity"] for g in gt}) != len(gt):
            raise ValueError("Duplicate ground-truth identity within a frame")
        for g in gt:
            wrist = np.asarray(g["wrist_xy"], dtype=float)
            if wrist.shape != (2,) or not np.isfinite(wrist).all() or np.any((wrist < 0) | (wrist > 1)):
                raise ValueError("Ground-truth wrist_xy must be finite normalized x,y")
        pred = [p for p in predictions[index]["hands"] if p["observed"]]
        matches = []
        if gt and pred:
            cost = np.array([[np.linalg.norm((np.array(g["wrist_xy"])-
                              np.array(p["image_xyz_raw"])[0, :2])*scale)
                              for p in pred] for g in gt])
            # Gate BEFORE assignment so an invalid edge cannot displace a valid one.
            gated = np.where(cost <= wrist_threshold, cost, 1e6)
            rows, cols = linear_sum_assignment(gated)
            matches = [(int(r), int(c)) for r, c in zip(rows, cols) if gated[r, c] < 1e6]
        tp += len(matches)
        fn += len(gt)-len(matches)
        fp += len(pred)-len(matches)
        for r, c in matches:
            g, p = gt[r], pred[c]
            identity = g["identity"]
            if identity in previous_ids and previous_ids[identity] != p["track_id"]:
                switches += 1
            previous_ids[identity] = p["track_id"]
            if "landmarks_xy" in g:
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
    return {
        "labeled_frames": len(seen_frames), "true_positives": tp,
        "false_positives": fp, "false_negatives": fn,
        "precision": tp/(tp+fp) if tp+fp else None,
        "recall": tp/(tp+fn) if tp+fn else None,
        "wrist_match_threshold_image_diagonal": wrist_threshold,
        "sampled_identity_switches": switches,
        "pck_on_matched_hands": points_correct/points_total if points_total else None,
        "pck_threshold_image_diagonal": pck_threshold,
        "labeled_joints_on_matched_hands": points_total,
        "mean_joint_error_image_diagonal": float(np.mean(distances)) if distances else None,
        "3d_error": None,
        "limitations": ["Only manually labeled frames are scored; sample bias may be substantial.",
                        "Identity changes between consecutive matched samples are counted, including across gaps.",
                        "PCK is conditional on matched detections and excludes missing/unlabeled joints.",
                        "2D annotations do not establish 3D accuracy; no 3D ground truth was provided."],
    }
