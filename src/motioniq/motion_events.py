"""Candidate motion events derived from a run's tracking data (RUN/motion_events.json).

Every event is INFERRED from observable tracking evidence and links to the frames it rests on.
None of them claims an action: a "candidate hold" means the wrist barely moved in the image for a
while, not that something was grasped; there is no object or contact model. Thresholds are
uncalibrated heuristics (no labelled events exist yet) and are recorded in the file.

Event types:
- ``hand_entry``: first observed frame of a track;
- ``hand_exit``: last observed frame before the track was lost for good (``out_of_view`` when the
  tracker inferred the hand left the image, otherwise ``track_lost``);
- ``long_gap``: a track unobserved for more than ``GAP_S`` seconds and then reacquired;
- ``candidate_hold``: 5-frame rolling-median wrist speed below ``HOLD_SPEED`` for at least ``HOLD_S``;
- ``candidate_movement``: rolling-median wrist speed above ``MOVE_SPEED`` for at least ``MOVE_S``.
Speeds are in image units per second (x, y normalised, aspect-corrected to the image diagonal), so
head motion also counts as hand motion: no camera-motion compensation.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

HOLD_SPEED, HOLD_S = .08, 1.
MOVE_SPEED, MOVE_S = .3, .3
GAP_S = 1.
SCHEMA = "motioniq_motion_events/0.1"


def _speed_runs(samples, test, min_s, window=5):
    """Runs of consecutive samples (< 0.1 s apart) where ``test`` holds on the ROLLING-MEDIAN speed
    (``window`` steps), so single-frame landmark spikes do not break a hold or a movement."""
    runs, stretch = [], [samples[0]]
    for a, b in zip(samples, samples[1:]):
        if 0 < b[0] - a[0] < .1:
            stretch.append(b)
        else:
            runs += _runs_in_stretch(stretch, test, min_s, window)
            stretch = [b]
    return runs + _runs_in_stretch(stretch, test, min_s, window)


def _runs_in_stretch(stretch, test, min_s, window):
    if len(stretch) < 3:
        return []
    speed = np.array([np.linalg.norm(b[1] - a[1])/(b[0] - a[0]) for a, b in zip(stretch, stretch[1:])])
    half = window//2
    smooth = np.array([np.median(speed[max(0, i - half):i + half + 1]) for i in range(len(speed))])
    runs, current = [], []
    for k, v in enumerate(smooth):
        if test(v):
            current = current or [stretch[k]]
            current.append(stretch[k + 1])
        else:
            if current and current[-1][0] - current[0][0] >= min_s:
                runs.append(current)
            current = []
    if current and current[-1][0] - current[0][0] >= min_s:
        runs.append(current)
    return runs


def derive_events(run: Path) -> dict:
    manifest = json.loads((run/"manifest.json").read_text()) if (run/"manifest.json").exists() else {}
    width = float((manifest.get("source") or {}).get("width") or 16)
    height = float((manifest.get("source") or {}).get("height") or 9)
    units = np.array([width, height])/np.hypot(width, height)
    tracks: dict[int, dict] = {}
    with (run/"landmarks.jsonl").open() as f:
        for line in f:
            frame = json.loads(line)
            for h in frame["hands"]:
                t = tracks.setdefault(h["track_id"], {"obs": [], "states": [], "sides": []})
                t["states"].append((frame["timestamp_s"], frame["frame_index"], h["state"], h.get("missing_reason")))
                if h["observed"] and h.get("image_xyz"):
                    t["obs"].append((frame["timestamp_s"], np.asarray(h["image_xyz"][0][:2])*units, frame["frame_index"], h))
                    t["sides"].append(h["side"])
    events = []

    def add(track_id, kind, t0, t1, frames, flags, basis):
        sides = tracks[track_id]["sides"]
        side = max(set(sides), key=sides.count) if sides else "unknown"
        events.append({"event_id": "", "track_id": track_id,
                       "hand": {"Left": "left", "Right": "right"}.get(side, "unknown"),
                       "event_type": kind, "start_time_s": round(t0, 4), "end_time_s": round(t1, 4),
                       "evidence_frames": frames, "status": "inferred", "quality_flags": flags,
                       "review_status": "unreviewed", "basis": basis})

    for tid, t in tracks.items():
        obs = t["obs"]
        if not obs:
            continue
        flags_for = lambda run: sorted({flag for _, _, _, h in run for flag in (
            ["side_unknown"] if h["side"] not in ("Left", "Right") else []) + (
            ["fitted_3d"] if h.get("world_source") == "fitted_from_2d" else [])})
        add(tid, "hand_entry", obs[0][0], obs[0][0], [obs[0][2]], flags_for(obs[:1]), "first observed frame of the track")
        last_state = t["states"][-1]
        if last_state[2] in ("lost", "retired"):
            reason = next((m for _, _, s, m in reversed(t["states"]) if m), None)
            add(tid, "hand_exit", obs[-1][0], last_state[0], [obs[-1][2]], flags_for(obs[-1:]),
                f"last observed frame; tracker reason afterwards: {reason or 'unknown'} (inferred)")
        for a, b in zip(obs, obs[1:]):
            if b[0] - a[0] > GAP_S:
                add(tid, "long_gap", a[0], b[0], [a[2], b[2]], [], f"track unobserved for {b[0] - a[0]:.2f} s, then reacquired")
        for kind, test, min_s, basis in (
                ("candidate_hold", lambda v: v < HOLD_SPEED, HOLD_S, f"wrist image speed < {HOLD_SPEED}/s for >= {HOLD_S} s"),
                ("candidate_movement", lambda v: v > MOVE_SPEED, MOVE_S, f"wrist image speed > {MOVE_SPEED}/s for >= {MOVE_S} s")):
            for run_ in _speed_runs(obs, test, min_s):
                mid = run_[len(run_)//2]
                add(tid, kind, run_[0][0], run_[-1][0], [run_[0][2], mid[2], run_[-1][2]], flags_for(run_), basis)
    events.sort(key=lambda e: (e["start_time_s"], e["track_id"], e["event_type"]))
    for n, e in enumerate(events):
        e["event_id"] = f"mev{n:05d}"
    return {"schema": SCHEMA, "events": events,
            "thresholds": {"hold_speed": HOLD_SPEED, "hold_s": HOLD_S, "move_speed": MOVE_SPEED, "move_s": MOVE_S, "speed": "5-frame rolling median",
                           "gap_s": GAP_S, "speed_units": "image diagonal fraction per second (no camera-motion compensation)"},
            "note": "Inferred candidates from tracking evidence; not validated against labelled events."}


def write_events(run: Path) -> Path:
    out = run/"motion_events.json"
    out.write_text(json.dumps(derive_events(run), indent=1) + "\n")
    return out
