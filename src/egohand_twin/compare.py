""""Flat video vs 3D" comparison of ONE moment, for teach-back and demo review.

Left: the source frame with the 2D landmark overlay, exactly as observed.
Right: each OBSERVED hand's MediaPipe hand-relative 3D landmarks
(``world_xyz_m_raw``, metres, origin moved to the wrist) drawn from three fixed
orthographic viewpoints at one shared scale, with a 2 cm grid.

What the 3D panel is and is not:
- It is MediaPipe's learned estimate of hand shape. Joints hidden in the image
  (back-of-hand views, cloth, fingers behind the palm) are model-inferred, NOT observed.
- Axes are MediaPipe's hand-relative axes (x approx. image right, y approx. image down,
  z approx. depth). On the test clip a PnP fit found them rotated by a median of
  30-39 degrees from an assumed camera frame, so "front/side/top" are approximate
  views, not calibrated camera or factory views.
- No predicted or lost track is drawn: the tool refuses frames without an observed hand
  and names the nearest frames that have one.

Outputs contain restricted footage: write them only under private run folders.
"""
from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

from .model import CONNECTIONS, sha256
from .render import BG, MUTED, PANEL, TEXT, color, fit_image, overlay, text

# Orthographic projections of hand-relative metres onto 2D panel axes (right, down).
VIEWS = {
    "front (x right, y down)": np.array([[1., 0, 0], [0, 1., 0]]),
    "side (z right, y down)": np.array([[0, 0, 1.], [0, 1., 0]]),
    "top (x right, z down)": np.array([[1., 0, 0], [0, 0, 1.]]),
}
PX_PER_M = 900.  # 2 cm = 18 px; a 0.2 m hand spans 180 px


def find_frame(run: Path, frame_index: int | None = None, time_s: float | None = None) -> dict:
    """Return the cached frame record (by exact index, or nearest timestamp_s)."""
    if (frame_index is None) == (time_s is None):
        raise ValueError("Give exactly one of frame_index or time_s")
    frames = [json.loads(line) for line in (run/"landmarks.jsonl").open()]
    if not frames:
        raise ValueError("Run has no frames")
    if frame_index is not None:
        match = [f for f in frames if f["frame_index"] == frame_index]
        if not match:
            raise ValueError(f"Frame {frame_index} was not processed in this run")
        chosen = match[0]
    else:
        chosen = min(frames, key=lambda f: abs(f["timestamp_s"]-time_s))
    if not any(h["observed"] for h in chosen["hands"]):
        observed = [f for f in frames if any(h["observed"] for h in f["hands"])]
        before = [f["frame_index"] for f in observed if f["frame_index"] < chosen["frame_index"]][-1:]
        after = [f["frame_index"] for f in observed if f["frame_index"] > chosen["frame_index"]][:1]
        raise ValueError(f"Frame {chosen['frame_index']} has no observed hand (3D is never shown for "
                         f"predicted/lost tracks). Nearest observed frames: before {before}, after {after}")
    return chosen


def read_frame(video: Path, frame_index: int) -> np.ndarray:
    """Sequential decode to the exact frame index (no seeking, so index <-> PTS stays exact)."""
    cap = cv2.VideoCapture(str(video))
    try:
        for i in range(frame_index + 1):
            ok = cap.grab()
            if not ok:
                raise ValueError("Video ended before the requested frame")
        ok, frame = cap.retrieve()
        if not ok:
            raise ValueError("Could not decode the requested frame")
        return frame
    finally:
        cap.release()


def draw_view(canvas, origin, projection, hand, title, size=(190, 250)):
    """One orthographic view of one hand, centred on the hand's mean point, shared scale."""
    x0, y0 = origin
    w, h = size
    cv2.rectangle(canvas, (x0, y0), (x0+w, y0+h), PANEL, -1)
    step = int(.02*PX_PER_M)
    for gx in range(x0 + (w//2) % step, x0+w, step):  # 2 cm grid
        cv2.line(canvas, (gx, y0), (gx, y0+h), (52, 46, 38), 1)
    for gy in range(y0 + (h//2) % step, y0+h, step):
        cv2.line(canvas, (x0, gy), (x0+w, gy), (52, 46, 38), 1)
    text(canvas, title, x0+5, y0+15, .38, MUTED)
    world = np.asarray(hand["world_xyz_m_raw"], float)
    flat = world @ projection.T * PX_PER_M
    points = flat - flat.mean(axis=0) + [x0+w//2, y0+h//2+8]
    clipped = bool(np.any((points < [x0, y0]) | (points > [x0+w-1, y0+h-1])))
    points = np.clip(points, [x0, y0], [x0+w-1, y0+h-1]).round().astype(int)
    c = color(hand)
    for a, b in CONNECTIONS:
        cv2.line(canvas, tuple(points[a]), tuple(points[b]), c, 2, cv2.LINE_AA)
    for p in points:
        cv2.circle(canvas, tuple(p), 3, c, -1, cv2.LINE_AA)
    cv2.circle(canvas, tuple(points[0]), 5, TEXT, 1, cv2.LINE_AA)  # wrist marker
    if clipped:
        text(canvas, "clipped", x0+w-60, y0+h-6, .38, (60, 60, 230))


def compare(video: Path, run: Path, out: Path, frame_index: int | None = None,
            time_s: float | None = None) -> dict:
    if out.exists():
        raise ValueError("Output exists; choose a new filename (never overwritten)")
    if not (run/"COMPLETE").exists():
        raise ValueError("Run is incomplete")
    manifest = json.loads((run/"manifest.json").read_text())
    if sha256(video) != manifest["source"]["sha256"]:
        raise ValueError("Source video does not match the cached run")
    record = find_frame(run, frame_index, time_s)
    observed = [h for h in record["hands"] if h["observed"]]
    frame = read_frame(video, record["frame_index"])
    canvas = np.full((900, 1600, 3), BG, np.uint8)
    text(canvas, "SAME MOMENT: FLAT VIDEO vs 3D HAND", 28, 44, .9, TEXT, 2)
    text(canvas, f'frame {record["frame_index"]}  |  t = {record["timestamp_s"]:.3f} s  |  '
                 f'source PTS {record["source_pts_s"]:.3f} s', 28, 74, .55, MUTED)
    canvas[110:110+540, 24:24+960] = fit_image(overlay(frame, record["hands"]), 960, 540)
    text(canvas, "Source frame + observed 2D landmarks", 28, 672, .5, MUTED)
    for row, hand in enumerate(observed[:2]):
        y0 = 110 + row*300
        p = hand.get("side_probability_right_smoothed")
        text(canvas, f'#{hand["track_id"]} {hand["side"]}' + (f' (p_right={p:.2f})' if p is not None else ''),
             1000, y0+16, .5, color(hand))
        for n, (title, projection) in enumerate(VIEWS.items()):
            draw_view(canvas, (1000 + n*200, y0+26), projection, hand, title)
    if len(observed) > 2:
        text(canvas, f"{len(observed)-2} more observed hand(s) not drawn", 1000, 720, .45, MUTED)
    y = 760
    for hand in observed:
        p = hand.get("side_probability_right_smoothed")
        side = f'{hand["side"]} (p_right={p:.2f})' if p is not None else hand["side"]
        text(canvas, f'#{hand["track_id"]} {side}  state={hand["state"]}  '
                     f'origin={hand.get("detection_origin") or "full_frame"}', 28, y, .5, color(hand))
        y += 24
    text(canvas, "3D = MediaPipe estimate, metres, hand-relative (circle = wrist, grid 2 cm). Joints hidden "
                 "in the image are model-inferred, not observed.", 28, 852, .47, TEXT)
    text(canvas, "Approximate views in MediaPipe axes - not calibrated camera or factory coordinates.",
         28, 878, .47, MUTED)
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), canvas)
    meta = {"image": str(out), "frame_index": record["frame_index"], "timestamp_s": record["timestamp_s"],
            "source_pts_s": record["source_pts_s"], "source_sha256": manifest["source"]["sha256"],
            "run": str(run),
            "hands": [{k: h.get(k) for k in ("track_id", "state", "side", "side_probability_right_smoothed",
                                              "detection_origin")} for h in observed],
            "coordinates": "world_xyz_m_raw minus wrist; MediaPipe hand-relative axes; metres",
            "note": "Hidden joints are model-inferred. Restricted footage: keep private."}
    out.with_suffix(".json").write_text(json.dumps(meta, indent=2)+"\n")
    return meta
