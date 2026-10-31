"""Task-specific, explainable quality assessment and a timestamped review queue.

Input: a completed run (cached landmarks.jsonl + manifest) and its source video.
No hand inference is repeated. The video is decoded once at low resolution for
cheap image statistics.

Assessments are for ONE task: inspecting hand motion. They are heuristics with
exposed components and thresholds, not a universal quality score:

- ``suitable``: observed hands cover most of the window and no listed problem fired.
- ``needs_review``: hands were observed, but evidence suggests the reconstruction
  may be incomplete or unreliable (gaps, fragmentation, side changes, jumps, blur,
  exposure, fast camera motion, hands at the image boundary).
- ``insufficient_evidence``: no observed hand in the window. This does NOT mean no
  hand was visible (the detector can miss hands) and does NOT mean the footage is
  bad (walking or looking around is legitimate and may suit other tasks).

Nothing is deleted or hidden; every item points back to source timestamps, frame
indices, track IDs and the processing run.
"""
from __future__ import annotations

import csv
from dataclasses import asdict, dataclass, field
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np

from .lift import bone_lengths
from .model import sha256

QUALITY_SCHEMA_VERSION = "0.1"


@dataclass
class QualityConfig:
    window_s: float = 1.0
    analysis_width: int = 320
    # Image signals (variance of Laplacian on a 320 px grayscale frame, etc.).
    blur_relative_to_clip_median_max: float = .6  # window median / processed-interval median
    overexposed_fraction_max: float = .15   # pixels >= 250
    underexposed_fraction_max: float = .25  # pixels <= 15
    camera_motion_pct_width_per_s_max: float = 40.  # global phase-correlation shift, % of frame width per second
    # Hand signals.
    suitable_coverage_min: float = .6
    gap_s_min: float = .5          # unobserved run while a track is still predicted/lost
    fragmentation_new_ids_min: int = 2
    landmark_jump_diag_per_s: float = 3.0   # wrist speed in image diagonals per second
    edge_margin: float = .02
    edge_fraction_min: float = .5
    bone_cv_max: float = .25
    merge_gap_s: float = 0.0       # adjacent flagged windows with this gap or less are merged
    max_item_s: float = 5.0        # queue items are split so a reviewer gets short intervals
    minor_reasons_for_review: int = 2  # a single minor reason is attached as a note only

    def digest(self) -> str:
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True).encode()).hexdigest()[:12]


ACTIONS = {
    "observation_gap": "Inspect interval; consider reprocessing with additional crops",
    "low_coverage": "Inspect interval; consider reprocessing with additional crops",
    "track_fragmentation": "Review identity continuity before using track IDs",
    "side_change": "Review left/right assignment",
    "landmark_jump": "Inspect for mis-association or landmark failure",
    "hand_at_image_edge": "Inspect for truncated hands; landmarks near the boundary may be extrapolated",
    "bone_length_inconsistency": "Inspect 3D posture; hand-relative scale is unstable",
    "blur": "Inspect for motion blur (sharpness well below this clip's median); detections may be missing",
    "overexposure": "Inspect exposure; detections may be missing",
    "underexposure": "Inspect exposure; detections may be missing",
    "fast_camera_motion": "Inspect; head motion may cause blur and track loss",
    "no_observed_hand": "Optional: check whether hands are visible but undetected",
}
MAJOR_REASONS = {"observation_gap", "low_coverage", "track_fragmentation", "landmark_jump"}
HAND_REASONS = {"observation_gap", "low_coverage", "track_fragmentation", "side_change",
                "landmark_jump", "hand_at_image_edge", "bone_length_inconsistency"}


def image_signals(video: Path, frame_indices: list[int], analysis_width: int = 320) -> dict[int, dict]:
    """Blur, exposure and global motion for the requested frames (single sequential decode)."""
    wanted = set(frame_indices)
    last = max(wanted)
    cap = cv2.VideoCapture(str(video))
    out, previous, index = {}, None, -1
    try:
        while index < last:
            ok = cap.grab()
            if not ok:
                raise ValueError("Video ended before all processed frames were analysed")
            index += 1
            if index not in wanted and index + 1 not in wanted:
                previous = None
                continue
            ok, frame = cap.retrieve()
            h, w = frame.shape[:2]
            small = cv2.resize(frame, (analysis_width, round(h*analysis_width/w)), interpolation=cv2.INTER_AREA)
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            if index in wanted:
                motion = None
                if previous is not None:
                    (dx, dy), _ = cv2.phaseCorrelate(previous.astype(np.float32), gray.astype(np.float32))
                    motion = float(np.hypot(dx, dy))/analysis_width
                out[index] = {"blur_laplacian_var": float(cv2.Laplacian(gray, cv2.CV_64F).var()),
                              "overexposed_fraction": float(np.mean(gray >= 250)),
                              "underexposed_fraction": float(np.mean(gray <= 15)),
                              "camera_shift_width_fraction": motion}
            previous = gray
    finally:
        cap.release()
    return out


@dataclass
class Window:
    start_s: float
    end_s: float
    frames: list = field(default_factory=list)


def _hand_frame_signals(frames: list[dict], cfg: QualityConfig, size=(16, 9)) -> list[dict]:
    """Per-frame hand signals from cached tracker output (observed data only for geometry)."""
    diag_units = np.asarray(size, float)/np.hypot(*size)
    last_obs: dict[int, tuple] = {}
    last_side: dict[int, str] = {}
    seen_ids: set[int] = set()
    rows = []
    for frame in frames:
        t = frame["timestamp_s"]
        observed = [h for h in frame["hands"] if h["observed"]]
        missing = [h for h in frame["hands"] if h["state"] in ("predicted", "lost")]
        new_ids = [h["track_id"] for h in observed if h["track_id"] not in seen_ids]
        seen_ids.update(new_ids)
        side_changes, jumps, edge, bone = [], [], 0, []
        for h in observed:
            tid = h["track_id"]
            image = np.asarray(h["image_xyz_raw"])
            if tid in last_side and last_side[tid] != h["side"]:
                side_changes.append(tid)
            last_side[tid] = h["side"]
            if tid in last_obs:
                t0, wrist0 = last_obs[tid]
                dt = t - t0
                if 0 < dt <= .2:
                    speed = float(np.linalg.norm((image[0, :2]-wrist0)*diag_units))/dt
                    if speed > cfg.landmark_jump_diag_per_s:
                        jumps.append({"track_id": tid, "wrist_speed_diag_per_s": round(speed, 3)})
            last_obs[tid] = (t, image[0, :2])
            xy = image[:, :2]
            near = np.mean((xy < cfg.edge_margin) | (xy > 1-cfg.edge_margin), axis=1) > 0
            edge += bool(np.mean(near) >= .1 or (xy[:, 1].max() > 1-cfg.edge_margin))
            bone.append((tid, bone_lengths(np.asarray(h["world_xyz_m_raw"]))))
        rows.append({"frame_index": frame["frame_index"], "timestamp_s": t,
                     "observed_hands": len(observed), "missing_tracks": [h["track_id"] for h in missing],
                     "observed_track_ids": [h["track_id"] for h in observed],
                     "new_track_ids": new_ids, "side_change_track_ids": side_changes,
                     "landmark_jumps": jumps, "hands_at_edge": edge, "bones": bone})
    return rows


def assess(run: Path, video: Path, cfg: QualityConfig | None = None) -> dict:
    cfg = cfg or QualityConfig()
    if not (run/"COMPLETE").exists():
        raise ValueError("Run is incomplete")
    manifest = json.loads((run/"manifest.json").read_text())
    source_hash = sha256(video)
    if source_hash != manifest["source"]["sha256"]:
        raise ValueError("Source video does not match the cached run")
    frames = [json.loads(line) for line in (run/"landmarks.jsonl").open()]
    if not frames:
        raise ValueError("Run has no frames")
    image = image_signals(video, [f["frame_index"] for f in frames], cfg.analysis_width)
    hand = _hand_frame_signals(frames, cfg, (manifest["source"]["width"], manifest["source"]["height"]))
    for row in hand:
        row.update(image[row["frame_index"]])
    # Convert per-frame camera shift to a per-second rate using actual PTS gaps.
    for prev, row in zip([None]+hand[:-1], hand):
        shift = row["camera_shift_width_fraction"]
        dt = row["timestamp_s"]-prev["timestamp_s"] if prev else None
        row["camera_motion_rate"] = (shift/dt*100 if shift is not None and dt and dt > 0 else None)

    clip_blur = float(np.median([r["blur_laplacian_var"] for r in hand]))
    # Fixed, non-overlapping windows aligned to the first processed timestamp.
    t0 = hand[0]["timestamp_s"]
    windows: dict[int, Window] = {}
    for row in hand:
        k = int((row["timestamp_s"]-t0)//cfg.window_s)
        windows.setdefault(k, Window(t0+k*cfg.window_s, t0+(k+1)*cfg.window_s)).frames.append(row)
    assessed = []
    for k in sorted(windows):
        w = windows[k]
        rows = w.frames
        n = len(rows)
        coverage = sum(r["observed_hands"] > 0 for r in rows)/n
        # Longest run of frames with a predicted/lost (i.e. recently seen, now missing) track.
        longest, current, start = 0., 0., None
        for r in rows:
            if r["missing_tracks"]:
                start = r["timestamp_s"] if start is None else start
                current = r["timestamp_s"]-start
                longest = max(longest, current)
            else:
                start = None
        new_ids = sorted({i for r in rows for i in r["new_track_ids"]})
        side_changes = sorted({i for r in rows for i in r["side_change_track_ids"]})
        jumps = [j for r in rows for j in r["landmark_jumps"]]
        edge_frames = sum(r["hands_at_edge"] > 0 for r in rows)
        observed_frames = sum(r["observed_hands"] > 0 for r in rows)
        per_track: dict[int, list] = {}
        for r in rows:
            for tid, lengths in r["bones"]:
                per_track.setdefault(tid, []).append(lengths)
        bone_cv = max((float(np.median(np.std(a, 0)/np.mean(a, 0))) for a in map(np.asarray, per_track.values())
                       if len(a) >= 5), default=None)
        blur = float(np.median([r["blur_laplacian_var"] for r in rows]))
        over = float(np.median([r["overexposed_fraction"] for r in rows]))
        under = float(np.median([r["underexposed_fraction"] for r in rows]))
        motions = [r["camera_motion_rate"] for r in rows if r["camera_motion_rate"] is not None]
        motion = float(np.median(motions)) if motions else None
        track_ids = sorted({i for r in rows for i in r["observed_track_ids"]} |
                           {i for r in rows for i in r["missing_tracks"]})
        evidence = {"frames": n, "observed_hand_frame_fraction": round(coverage, 3),
                    "longest_missing_track_s": round(longest, 3), "new_track_ids": new_ids,
                    "side_change_track_ids": side_changes, "landmark_jumps": len(jumps),
                    "edge_frame_fraction_of_observed": round(edge_frames/observed_frames, 3) if observed_frames else None,
                    "max_track_median_bone_cv": round(bone_cv, 3) if bone_cv is not None else None,
                    "median_blur_laplacian_var": round(blur, 1),
                    "blur_relative_to_clip_median": round(blur/clip_blur, 3), "median_overexposed_fraction": round(over, 3),
                    "median_underexposed_fraction": round(under, 3),
                    "median_camera_motion_rate": round(motion, 3) if motion is not None else None}
        reasons = []
        if observed_frames:
            if longest >= cfg.gap_s_min:
                reasons.append("observation_gap")
            if coverage < cfg.suitable_coverage_min:
                reasons.append("low_coverage")
            if len(new_ids) >= cfg.fragmentation_new_ids_min:
                reasons.append("track_fragmentation")
            if side_changes:
                reasons.append("side_change")
            if jumps:
                reasons.append("landmark_jump")
            if edge_frames/observed_frames >= cfg.edge_fraction_min:
                reasons.append("hand_at_image_edge")
            if bone_cv is not None and bone_cv > cfg.bone_cv_max:
                reasons.append("bone_length_inconsistency")
        if blur < cfg.blur_relative_to_clip_median_max*clip_blur:
            reasons.append("blur")
        if over > cfg.overexposed_fraction_max:
            reasons.append("overexposure")
        if under > cfg.underexposed_fraction_max:
            reasons.append("underexposure")
        if motion is not None and motion > cfg.camera_motion_pct_width_per_s_max:
            reasons.append("fast_camera_motion")
        minor = [r for r in reasons if r not in MAJOR_REASONS]
        if not observed_frames:
            status = "insufficient_evidence"
            reasons = ["no_observed_hand"] + reasons
        elif any(r in MAJOR_REASONS for r in reasons) or len(minor) >= cfg.minor_reasons_for_review:
            status = "needs_review"
        else:
            status = "suitable"  # any single minor reason is kept as a note
        assessed.append({"start_s": round(w.start_s, 6), "end_s": round(w.end_s, 6),
                         "first_frame": rows[0]["frame_index"], "last_frame": rows[-1]["frame_index"],
                         "status": status, "reasons": reasons, "track_ids": track_ids, "evidence": evidence})
    queue = build_queue(assessed, cfg)
    run_id = hashlib.sha256((run/"manifest.json").read_bytes()).hexdigest()[:12]
    duration = hand[-1]["timestamp_s"] - t0 + (cfg.window_s if len(hand) == 1 else 0)
    by_status = {s: sum(w["end_s"]-w["start_s"] for w in assessed if w["status"] == s)
                 for s in ("suitable", "needs_review", "insufficient_evidence")}
    reason_counts: dict[str, int] = {}
    for w in assessed:
        for r in w["reasons"]:
            reason_counts[r] = reason_counts.get(r, 0)+1
    review_items = [q for q in queue if q["status"] == "needs_review"]
    summary = {
        "schema_version": QUALITY_SCHEMA_VERSION,
        "task": "hand-motion inspection (task-specific; not a general footage-quality score)",
        "assessment_type": "heuristic (thresholds below; not learned, not human-reviewed)",
        "source": {"name": manifest["source"]["name"], "sha256": source_hash},
        "run": {"path": str(run), "manifest_sha256_12": run_id,
                "parameters": manifest.get("parameters")},
        "config": {**asdict(cfg), "digest": cfg.digest()},
        "processed_frames": len(hand), "interval_s": [t0, hand[-1]["timestamp_s"]],
        "windows": len(assessed),
        "seconds_by_status": {k: round(v, 3) for k, v in by_status.items()},
        "window_reason_counts": dict(sorted(reason_counts.items())),
        "review_items": len(review_items),
        "review_items_per_minute": round(len(review_items)/max(duration/60, 1e-9), 3),
        "queue_items_total": len(queue),
        "limitations": [
            "insufficient_evidence means no OBSERVED hand; hands may still be visible but undetected.",
            "No visible hand is not poor footage: walking or looking around may suit other tasks.",
            "Thresholds were set by inspection of the development interval; they are not validated on other clips or recording families.",
            "Handedness score is not landmark quality and is not used as one.",
            "Image statistics are global and cannot confirm occlusion or blur on the hand itself."],
    }
    return {"summary": summary, "windows": assessed, "queue": queue, "frames": hand, "run_id": run_id}


def build_queue(windows: list[dict], cfg: QualityConfig) -> list[dict]:
    """Merge consecutive windows with the same status into timestamped review items."""
    items: list[dict] = []
    for w in windows:
        prev = items[-1] if items else None
        if prev and prev["status"] == w["status"] and w["start_s"]-prev["end_s"] <= cfg.merge_gap_s + 1e-9 \
                and w["end_s"]-prev["start_s"] <= cfg.max_item_s + 1e-9:
            prev["end_s"], prev["last_frame"] = w["end_s"], w["last_frame"]
            prev["track_ids"] = sorted(set(prev["track_ids"]) | set(w["track_ids"]))
            for r in w["reasons"]:
                prev["reason_window_counts"][r] = prev["reason_window_counts"].get(r, 0)+1
            prev["windows"].append({k: w[k] for k in ("start_s", "end_s", "reasons", "evidence")})
            continue
        items.append({"status": w["status"], "start_s": w["start_s"], "end_s": w["end_s"],
                      "first_frame": w["first_frame"], "last_frame": w["last_frame"],
                      "track_ids": list(w["track_ids"]),
                      "reason_window_counts": {r: 1 for r in w["reasons"]},
                      "windows": [{k: w[k] for k in ("start_s", "end_s", "reasons", "evidence")}]})
    for i, item in enumerate(items):
        reasons = item["reason_window_counts"]
        hand_reasons = [r for r in reasons if r in HAND_REASONS]
        # Priority: needs_review intervals with hand-reconstruction problems first,
        # weighted by how many windows show them; image-only flags rank lower.
        item["priority_score"] = (sum(reasons[r] for r in MAJOR_REASONS & set(reasons))*3 +
                                  sum(reasons[r] for r in hand_reasons)*2 + sum(
            v for r, v in reasons.items() if r not in HAND_REASONS and r != "no_observed_hand")) \
            if item["status"] == "needs_review" else 0
        item["suggested_actions"] = sorted({ACTIONS[r] for r in reasons})
        item["assessment_source"] = "heuristic"
        item["item_id"] = f"Q{i:04d}"
    return items


def write_quality(run: Path, video: Path, out: Path | None = None, cfg: QualityConfig | None = None) -> dict:
    result = assess(run, video, cfg)
    out = out or run/"quality"
    out.mkdir(parents=True, exist_ok=True)
    source = result["summary"]["source"]
    (out/"quality_summary.json").write_text(json.dumps(result["summary"], indent=2)+"\n")
    (out/"quality_windows.json").write_text(json.dumps(result["windows"], indent=1)+"\n")
    queue = [{"source": source["name"], "source_sha256": source["sha256"], "run_id": result["run_id"], **q}
             for q in result["queue"]]
    (out/"review_queue.json").write_text(json.dumps(queue, indent=1)+"\n")
    ranked = sorted([q for q in queue if q["status"] == "needs_review"],
                    key=lambda q: (-q["priority_score"], q["start_s"]))
    with (out/"review_queue.csv").open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["rank", "item_id", "status", "start_s", "end_s", "first_frame", "last_frame",
                         "track_ids", "reasons", "priority_score", "suggested_actions",
                         "assessment_source", "source", "run_id"])
        others = [q for q in queue if q["status"] != "needs_review"]
        for rank, q in enumerate(ranked + others, 1):
            writer.writerow([rank if q["status"] == "needs_review" else "", q["item_id"], q["status"],
                             f'{q["start_s"]:.3f}', f'{q["end_s"]:.3f}', q["first_frame"], q["last_frame"],
                             " ".join(map(str, q["track_ids"])),
                             " ".join(f"{r}x{n}" for r, n in sorted(q["reason_window_counts"].items())),
                             q["priority_score"], " | ".join(q["suggested_actions"]),
                             q["assessment_source"], q["source"], q["run_id"]])
    with (out/"quality_frames.csv").open("w", newline="") as f:
        keys = ["frame_index", "timestamp_s", "observed_hands", "hands_at_edge", "blur_laplacian_var",
                "overexposed_fraction", "underexposed_fraction", "camera_motion_rate"]
        writer = csv.DictWriter(f, fieldnames=keys+["missing_tracks", "new_track_ids", "side_change_track_ids",
                                                    "landmark_jumps"])
        writer.writeheader()
        for r in result["frames"]:
            writer.writerow({**{k: r[k] for k in keys}, "missing_tracks": " ".join(map(str, r["missing_tracks"])),
                             "new_track_ids": " ".join(map(str, r["new_track_ids"])),
                             "side_change_track_ids": " ".join(map(str, r["side_change_track_ids"])),
                             "landmark_jumps": len(r["landmark_jumps"])})
    return result["summary"]


def evaluate_quality(windows: list[dict], labels: Path, evaluation: dict, split: str | None = None) -> dict:
    """Compare window assessments with labeled frames.

    Uses the detection evaluation (same run, same labels) to classify each labeled
    frame: ``missed`` (>=1 labeled visible hand not matched), ``all_matched``
    (visible hands, all matched) or ``no_visible_hand``. A good flagger puts missed
    frames in flagged windows and keeps all_matched frames in suitable windows.
    """
    data = json.loads(labels.read_text())
    frames = [f for f in data["frames"] if split is None or f.get("split") == split]
    missed = {m["frame_index"] for m in evaluation["missed_hands"]}
    def window_for(t):
        for w in windows:
            if w["start_s"] - 1e-9 <= t < w["end_s"]:
                return w
        return None
    table: dict[str, dict[str, int]] = {}
    for f in frames:
        t = f.get("timestamp_s")
        w = window_for(t) if t is not None else None
        if w is None:
            continue
        kind = ("no_visible_hand" if not f["hands"] else "missed" if f["frame_index"] in missed else "all_matched")
        table.setdefault(kind, {}).setdefault(w["status"], 0)
        table[kind][w["status"]] += 1
    def count(kind, statuses):
        return sum(table.get(kind, {}).get(s, 0) for s in statuses)
    flagged = ("needs_review", "insufficient_evidence")
    n_missed, n_good, n_none = (sum(table.get(k, {}).values()) for k in ("missed", "all_matched", "no_visible_hand"))
    return {
        "label_status": evaluation.get("label_status"), "split": split,
        "frames_by_kind_and_window_status": table,
        "missed_frames_in_flagged_windows": {"k": count("missed", flagged), "n": n_missed},
        "all_matched_frames_in_suitable_windows": {"k": count("all_matched", ["suitable"]), "n": n_good},
        "all_matched_frames_flagged_needs_review": {"k": count("all_matched", ["needs_review"]), "n": n_good},
        "insufficient_evidence_frames_with_visible_hand": {
            "k": count("missed", ["insufficient_evidence"]),
            "n": count("missed", ["insufficient_evidence"]) + count("no_visible_hand", ["insufficient_evidence"])},
        "note": ("Frame-level comparison on sparse labels; a window is judged by the labeled frames inside it. "
                 "'missed' uses the same wrist-matching protocol as egohand evaluate."),
    }


def export_segments(run: Path, out: Path, status: str = "suitable", quality_dir: Path | None = None) -> dict:
    """Write cached hand records for every queue interval with ``status``.

    Records are copied unchanged from landmarks.jsonl (raw and filtered values,
    explicit states; predicted tracks keep 2D-only data and lost tracks none).
    Nothing is removed from the source run; excluded intervals are simply not copied.
    """
    quality_dir = quality_dir or run/"quality"
    queue = json.loads((quality_dir/"review_queue.json").read_text())
    summary = json.loads((quality_dir/"quality_summary.json").read_text())
    items = [q for q in queue if q["status"] == status]
    if out.exists() and any(out.iterdir()):
        raise ValueError("Choose an empty export directory")
    out.mkdir(parents=True, exist_ok=True)
    frames = {}
    with (run/"landmarks.jsonl").open() as f:
        for line in f:
            frame = json.loads(line)
            frames[frame["frame_index"]] = frame
    index = []
    for item in items:
        name = f'{item["item_id"]}_{item["start_s"]:08.3f}-{item["end_s"]:08.3f}.jsonl'
        observed = 0
        with (out/name).open("w") as f:
            for i in range(item["first_frame"], item["last_frame"]+1):
                if i in frames:
                    f.write(json.dumps(frames[i], separators=(",", ":"))+"\n")
                    observed += sum(h["observed"] for h in frames[i]["hands"])
        index.append({"file": name, "item_id": item["item_id"], "start_s": item["start_s"], "end_s": item["end_s"],
                      "first_frame": item["first_frame"], "last_frame": item["last_frame"],
                      "track_ids": item["track_ids"], "observed_hand_records": observed})
    manifest = {"export_status": status, "segments": index,
                "source": summary["source"], "run": summary["run"],
                "quality_config_digest": summary["config"]["digest"],
                "coordinates": "As in landmarks.jsonl: normalized image xyz and MediaPipe hand-relative meters; "
                               "not camera or factory coordinates.",
                "note": "Selection is a heuristic quality assessment, not human review."}
    (out/"segments_manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")
    return manifest
