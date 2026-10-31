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
