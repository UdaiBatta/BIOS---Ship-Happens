"""Annotation-set generation for split-aware, provenance-tracked hand labels.

Frames are sampled from explicit source intervals so that adjacent frames stay in
one split (development or holdout). The generated template is UNLABELED and
cannot be scored until a person fills it in. Grid overlays help an annotator read
normalized coordinates; they never contain model predictions, so labels can be
made before inspecting detector output.
"""
from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

from .model import sha256

LABEL_SCHEMA_VERSION = "2.0"
SIDES = ("wearer_left", "wearer_right", "other", "unknown")
VISIBILITY = ("full", "truncated", "occluded")
LABELABLE_DEFINITION = (
    "A hand is labelable when some of the palm or back of the hand (the region between "
    "wrist and knuckles) is visible in the image. Fingertip-only or forearm-only views "
    "are not labelable. Every labelable hand in a frame must be listed, including other "
    "people's hands. wrist_xy is the center of the wrist joint (MediaPipe landmark 0) in "
    "normalized source-image x/width, y/height. If the wrist is just outside the image it "
    "may be extrapolated with wrist_in_frame=false.")


def parse_intervals(text: str) -> list[tuple[float, float]]:
    intervals = []
    for part in text.split(","):
        start, end = (float(v) for v in part.split(":"))
        if not 0 <= start < end:
            raise ValueError("Intervals must be start:end seconds with 0 <= start < end")
        intervals.append((start, end))
    if any(start < prev_end for (_, prev_end), (start, _) in zip(sorted(intervals), sorted(intervals)[1:])):
        raise ValueError("Annotation intervals must not overlap")
    return intervals


def grid(image: np.ndarray, step: float = .05) -> np.ndarray:
    """Overlay a normalized-coordinate grid; labels every 0.1."""
    out = image.copy()
    h, w = out.shape[:2]
    for k in range(1, round(1/step)):
        v = k*step
        major = k % 2 == 0
        c = (0, 255, 255) if major else (0, 160, 160)
        x, y = round(v*w), round(v*h)
        cv2.line(out, (x, 0), (x, h), c, 1, cv2.LINE_AA)
        cv2.line(out, (0, y), (w, y), c, 1, cv2.LINE_AA)
        if major:
            for label, pos in [(f"{v:.1f}", (x+2, 14)), (f"{v:.1f}", (x+2, h-4)),
                               (f"{v:.1f}", (2, y-3)), (f"{v:.1f}", (w-30, y-3))]:
                cv2.putText(out, label, pos, cv2.FONT_HERSHEY_SIMPLEX, .42, (0, 0, 0), 3, cv2.LINE_AA)
                cv2.putText(out, label, pos, cv2.FONT_HERSHEY_SIMPLEX, .42, (0, 255, 255), 1, cv2.LINE_AA)
    return out


def make_annotation_set(video: Path, out: Path, timestamps: list[float],
                        intervals: list[tuple[float, float]], step_frames: int, split: str,
                        tile_width: int = 960) -> dict:
    intervals = sorted(intervals)
    if any(start < 0 or start >= end for start, end in intervals):
        raise ValueError("Intervals must be start:end seconds with 0 <= start < end")
    if any(start < prev_end for (_, prev_end), (start, _) in zip(intervals, intervals[1:])):
        raise ValueError("Annotation intervals must not overlap")
    if out.exists() and any(out.iterdir()):
        raise ValueError("Choose an empty annotation output directory")
    relative = np.asarray(timestamps) - timestamps[0]
    selected: list[tuple[int, str]] = []
    for start, end in intervals:
        eligible = np.flatnonzero((relative >= start) & (relative < end))
        name = f"{split}_{start:07.2f}_{end:07.2f}"
        selected += [(int(i), name) for i in eligible[::step_frames]]
    if not selected:
        raise ValueError("No frames in requested annotation intervals")
    out.mkdir(parents=True)
    (out/"frames").mkdir()
    cap = cv2.VideoCapture(str(video))
    tiles, frames = [], []
    wanted = {i for i, _ in selected}
    index = -1
    try:
        while wanted:
            ok, image = cap.read()
            if not ok:
                raise ValueError("Video ended before all annotation frames were read")
            index += 1
            if index not in wanted:
                continue
            wanted.discard(index)
            cv2.imwrite(str(out/"frames"/f"frame_{index:06}.jpg"), image, [cv2.IMWRITE_JPEG_QUALITY, 95])
            h, w = image.shape[:2]
            small = cv2.resize(image, (tile_width, round(h*tile_width/w)))
            tile = grid(small)
            cv2.putText(tile, f"F{index}  t={relative[index]:.2f}s", (40, 40), cv2.FONT_HERSHEY_SIMPLEX,
                        .9, (0, 0, 0), 5, cv2.LINE_AA)
            cv2.putText(tile, f"F{index}  t={relative[index]:.2f}s", (40, 40), cv2.FONT_HERSHEY_SIMPLEX,
                        .9, (255, 255, 255), 2, cv2.LINE_AA)
            tiles.append((index, tile))
    finally:
        cap.release()
    tiles.sort()
    (out/"sheets").mkdir()
    for n in range(0, len(tiles), 4):
        group = [t for _, t in tiles[n:n+4]]
        while len(group) < 4:
            group.append(np.zeros_like(group[0]))
        sheet = np.vstack([np.hstack(group[:2]), np.hstack(group[2:])])
        cv2.imwrite(str(out/"sheets"/f"sheet_{n//4:03}_F{tiles[n][0]}.jpg"), sheet,
                    [cv2.IMWRITE_JPEG_QUALITY, 90])
    interval_of = dict(selected)
    for i, _ in selected:
        frames.append({"frame_index": i, "timestamp_s": round(float(relative[i]), 6),
                       "split": split, "interval": interval_of[i], "complete": False, "hands": []})
    template = {
        "schema_version": LABEL_SCHEMA_VERSION,
        "source_sha256": sha256(video),
        "reviewed": False,
        "provenance": {"annotator": None, "method": None, "model_assisted": None,
                       "predictions_viewed_before_labeling": None},
        "labelable_definition": LABELABLE_DEFINITION,
        "allowed_sides": list(SIDES), "allowed_visibility": list(VISIBILITY),
        "instructions": ("UNLABELED TEMPLATE. For each frame list ALL labelable hands with gt_id "
                         "(short-term identity, stable within an interval), side, wrist_xy, "
                         "visibility and optional tags; set complete=true once done. Keep "
                         "reviewed=false until an independent human has checked the labels."),
        "frames": frames,
    }
    (out/"labels.template.json").write_text(json.dumps(template, indent=2)+"\n")
    return template


REVIEW_COLUMNS = ["frame_index", "timestamp_s", "split", "gt_id", "side", "visibility", "wrist_x", "wrist_y",
                  "wrist_in_frame", "tags", "decision", "corrected_side", "corrected_wrist_x",
                  "corrected_wrist_y", "corrected_visibility", "missing_hand_note", "reviewer_note"]
DECISIONS = {"ok", "fix", "delete", "unsure"}


def label_review_pack(video: Path, labels: Path, out: Path, tile_width: int = 960) -> dict:
    """Sheets with every provisional label drawn on its frame, plus a review CSV.

    The reviewer checks each drawn wrist/side/visibility, fills ``decision`` (ok | fix |
    delete | unsure) and corrections, and notes any MISSING hand per frame in
    ``missing_hand_note``. Frames without hands get one row (gt_id empty) so missing
    hands can be reported there. Predictions are never drawn, to keep review independent.
    """
    import csv
    if out.exists() and any(out.iterdir()):
        raise ValueError("Choose an empty review output directory")
    data = json.loads(Path(labels).read_text())
    frames = sorted(data["frames"], key=lambda f: f["frame_index"])
    wanted = {f["frame_index"]: f for f in frames}
    out.mkdir(parents=True)
    colours = {"wearer_left": (63, 216, 155), "wearer_right": (66, 171, 255), "other": (220, 120, 255),
               "unknown": (200, 200, 200)}
    tiles = []
    cap = cv2.VideoCapture(str(video))
    index = -1
    try:
        while len(tiles) < len(wanted):
            ok, image = cap.read()
            if not ok:
                raise ValueError("Video ended before all labeled frames were read")
            index += 1
            if index not in wanted:
                continue
            h, w = image.shape[:2]
            tile = cv2.resize(image, (tile_width, round(h*tile_width/w)))
            th, tw = tile.shape[:2]
            frame = wanted[index]
            for hand in frame["hands"]:
                x, y = hand["wrist_xy"]
                p = (int(np.clip(x, 0, 1)*tw), int(np.clip(y, 0, 1)*th))
                c = colours.get(hand["side"], (200, 200, 200))
                cv2.circle(tile, p, 9, (0, 0, 0), 4)
                cv2.circle(tile, p, 9, c, 2)
                cv2.drawMarker(tile, p, c, cv2.MARKER_CROSS, 14, 1)
                label = f'{hand["gt_id"].split(":")[-1]} {hand["side"]} {hand["visibility"]}' + \
                        ("" if hand.get("wrist_in_frame", True) else " (wrist outside)")
                org = (min(p[0]+12, tw-260), max(p[1]-12, 20))
                cv2.putText(tile, label, org, cv2.FONT_HERSHEY_SIMPLEX, .55, (0, 0, 0), 4, cv2.LINE_AA)
                cv2.putText(tile, label, org, cv2.FONT_HERSHEY_SIMPLEX, .55, c, 1, cv2.LINE_AA)
            title = f'F{index} t={frame.get("timestamp_s", 0):.2f}s {frame.get("split", "")}  hands={len(frame["hands"])}'
            cv2.putText(tile, title, (12, 30), cv2.FONT_HERSHEY_SIMPLEX, .8, (0, 0, 0), 5, cv2.LINE_AA)
            cv2.putText(tile, title, (12, 30), cv2.FONT_HERSHEY_SIMPLEX, .8, (255, 255, 255), 2, cv2.LINE_AA)
            tiles.append((index, tile))
    finally:
        cap.release()
    for n in range(0, len(tiles), 4):
        group = [t for _, t in tiles[n:n+4]]
        while len(group) < 4:
            group.append(np.zeros_like(group[0]))
        sheet = np.vstack([np.hstack(group[:2]), np.hstack(group[2:])])
        cv2.imwrite(str(out/f"review_{n//4:03}_F{tiles[n][0]}.jpg"), sheet, [cv2.IMWRITE_JPEG_QUALITY, 90])
    with (out/"review.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=REVIEW_COLUMNS)
        writer.writeheader()
        for frame in frames:
            base = {"frame_index": frame["frame_index"], "timestamp_s": frame.get("timestamp_s"),
                    "split": frame.get("split")}
            if not frame["hands"]:
                writer.writerow({**base, "gt_id": "", "decision": ""})
            for hand in frame["hands"]:
                writer.writerow({**base, "gt_id": hand["gt_id"], "side": hand["side"],
                                 "visibility": hand["visibility"], "wrist_x": hand["wrist_xy"][0],
                                 "wrist_y": hand["wrist_xy"][1],
                                 "wrist_in_frame": hand.get("wrist_in_frame", True),
                                 "tags": " ".join(hand.get("tags", [])), "decision": ""})
    rows = sum(max(1, len(f["hands"])) for f in frames)
    (out/"README.txt").write_text(
        "Review each sheet: circles are the provisional wrist labels (green wearer_left, orange wearer_right,\n"
        "grey unknown). In review.csv set decision = ok | fix | delete | unsure for every hand row; for 'fix'\n"
        "fill corrected_* columns (normalized 0-1 coordinates; read them from the frame grid sheets).\n"
        "If a visible hand has NO circle, describe it in missing_hand_note on that frame's row.\n"
        "Rows without gt_id are frames labeled as having no hands: leave decision empty or write 'ok'.\n"
        "Then run: egohand label-review-apply LABELS review.csv --reviewer INITIALS --out NEW_LABELS.json\n")
    return {"frames": len(frames), "rows": rows, "sheets": (len(tiles)+3)//4, "out": str(out)}


def apply_label_review(labels: Path, review_csv: Path, reviewer: str, out: Path) -> dict:
    """Merge a filled review.csv into a NEW labels file.

    ``reviewed`` becomes true only when every hand row has decision ok/fix/delete and no
    frame reports a missing hand; otherwise the output stays provisional and lists what is open.
    The input labels file is never modified and the output is never overwritten.
    """
    import csv
    if out.exists():
        raise ValueError("Output labels file exists; never overwritten")
    if not reviewer.strip():
        raise ValueError("reviewer initials are required")
    data = json.loads(Path(labels).read_text())
    by_key = {(f["frame_index"], h["gt_id"]): h for f in data["frames"] for h in f["hands"]}
    expected = {(f["frame_index"], h["gt_id"]) for f in data["frames"] for h in f["hands"]}
    expected.update((f["frame_index"], "") for f in data["frames"] if not f["hands"])
    with Path(review_csv).open(newline="") as f:
        rows = list(csv.DictReader(f))
    seen = set()
    for row in rows:
        try:
            key = (int(row["frame_index"]), row["gt_id"])
        except (KeyError, TypeError, ValueError):
            raise ValueError("Review CSV contains an invalid frame or hand row") from None
        if key not in expected:
            raise ValueError(f"review row for unknown hand {key[0]}/{key[1]}")
        if key in seen:
            raise ValueError(f"duplicate review row {key[0]}/{key[1]}")
        seen.add(key)
    missing = expected - seen
    if missing:
        frame_index, gt_id = sorted(missing)[0]
        raise ValueError(f"missing review row {frame_index}/{gt_id}")
    open_items, counts = [], {d: 0 for d in DECISIONS}
    deletions = set()
    for row in rows:
        frame_index = int(row["frame_index"])
        if row.get("missing_hand_note", "").strip():
            open_items.append(f"frame {frame_index}: missing hand reported: {row['missing_hand_note'].strip()}")
        if not row["gt_id"]:
            if row["decision"].strip().lower() not in ("", "ok"):
                raise ValueError(f"frame {frame_index}: no-hand row decision must be empty or ok")
            continue
        decision = row["decision"].strip().lower()
        hand = by_key[(frame_index, row["gt_id"])]
        if decision not in DECISIONS:
            open_items.append(f"frame {frame_index} {row['gt_id']}: no decision")
            continue
        counts[decision] += 1
        if decision == "unsure":
            open_items.append(f"frame {frame_index} {row['gt_id']}: marked unsure")
        elif decision == "delete":
            deletions.add((frame_index, row["gt_id"]))
        elif decision == "fix":
            side, vis = row["corrected_side"].strip(), row["corrected_visibility"].strip()
            if side and side not in SIDES:
                raise ValueError(f"frame {frame_index} {row['gt_id']}: corrected_side must be one of {SIDES}")
            if vis and vis not in VISIBILITY:
                raise ValueError(f"frame {frame_index} {row['gt_id']}: corrected_visibility must be one of {VISIBILITY}")
            hand["side"] = side or hand["side"]
            hand["visibility"] = vis or hand["visibility"]
            x, y = row["corrected_wrist_x"].strip(), row["corrected_wrist_y"].strip()
            if bool(x) != bool(y):
                raise ValueError(f"frame {frame_index} {row['gt_id']}: both corrected wrist coordinates are required")
            if x and y:
                xy = [float(x), float(y)]
                if not all(-.25 <= v <= 1.25 for v in xy):
                    raise ValueError(f"frame {frame_index} {row['gt_id']}: corrected wrist must be normalized")
                hand["wrist_xy"] = xy
                hand["wrist_in_frame"] = all(0 <= v <= 1 for v in xy)
        if row["reviewer_note"].strip():
            hand.setdefault("review_note", row["reviewer_note"].strip())
    for frame in data["frames"]:
        frame["hands"] = [h for h in frame["hands"] if (frame["frame_index"], h["gt_id"]) not in deletions]
    complete = not open_items
    data["reviewed"] = complete
    data["label_status"] = "reviewed" if complete else "provisional"
    data.setdefault("provenance", {})["independent_human_review"] = complete
    data["review"] = {"reviewer": reviewer.strip(), "decisions": counts, "open_items": open_items,
                      "source_review_csv": str(review_csv)}
    out.write_text(json.dumps(data, indent=1)+"\n")
    return data["review"] | {"reviewed": complete}
