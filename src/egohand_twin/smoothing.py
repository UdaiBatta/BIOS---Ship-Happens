"""Offline landmark smoothing: wrist by forward-backward Kalman, fingers by One Euro relative to the wrist.

Why it replaced the online One Euro filter (measured against labelled wrists, provisional labels):
the old filter used beta 0.03 in normalised image units, where hand speeds are ~0.5 units/s, so it
acted as a fixed 1.7 Hz low-pass and lagged ~65-80 px behind fast hands. Median wrist error rose
from 28.7 px (raw) to 48.1 px on dev, and from 25.3 to 45.3 px on holdout.

This smoother (chosen on dev, checked once on holdout):
- the wrist (joint 0) runs through a constant-velocity Kalman filter forward, then a
  Rauch-Tung-Striebel pass backward, so it uses the future as well as the past and does not lag
  (offline runs only);
- the other 20 joints run through One Euro (min_cutoff 1.0 Hz, beta 0.05 per px/s) applied to
  their offset from the RAW wrist, so finger articulation is stabilised separately from hand
  translation, then are added back to the smoothed wrist;
- hand-relative 3D (world_xyz_m) uses the same One Euro relative to its wrist, with beta scaled
  to metres (about 1200 px per metre for a hand on this footage).

Segments are one track's consecutive observed frames. A gap over 0.2 s or any non-observed frame
ends the segment, so nothing is smoothed across a loss or between different tracks. Raw values
(`image_xyz_raw`, `world_xyz_m_raw`) are never modified. Image z (relative depth) is left raw.

Holdout: wrist error median 26.6 px (raw 25.3, old 45.3), wrist jitter 16.2 -> 8.1 px,
fingertip jitter 21.9 -> 12.7 px, fast-motion offset from raw 65 -> 6 px.
"""
from __future__ import annotations

import numpy as np

from .tracking import OneEuro

GAP_S = .2
WRIST_Q = 4000.     # px/s^2: Kalman process noise (acceleration) for the wrist
WRIST_R = 4.        # px: measurement noise
FINGER_MIN_CUTOFF, FINGER_BETA = 1., .05      # Hz, per px/s
PX_PER_METRE = 1200.


def rts_wrist(times: np.ndarray, points: np.ndarray, q: float = WRIST_Q, r: float = WRIST_R) -> np.ndarray:
    """Constant-velocity Kalman forward pass + Rauch-Tung-Striebel backward pass for (n, 2) pixels."""
    n = len(points)
    if n < 2:
        return points.copy()
    H = np.array([[1., 0, 0, 0], [0, 1, 0, 0]])
    R = np.eye(2)*r**2
    xf, Pf = np.zeros((n, 4)), np.zeros((n, 4, 4))
    xp, Pp, Fs = np.zeros((n, 4)), np.zeros((n, 4, 4)), np.zeros((n, 4, 4))
    x, P = np.array([*points[0], 0., 0.]), np.diag([r**2, r**2, 1e6, 1e6])
    for i in range(n):
        dt = max(times[i] - times[i - 1], 1e-3) if i else 0.
        F = np.array([[1., 0, dt, 0], [0, 1, 0, dt], [0, 0, 1, 0], [0, 0, 0, 1]])
        G = np.array([[dt*dt/2, 0], [0, dt*dt/2], [dt, 0], [0, dt]])
        Fs[i] = F
        xp[i], Pp[i] = (F @ x, F @ P @ F.T + G @ G.T*q*q) if i else (x, P)
        K = Pp[i] @ H.T @ np.linalg.inv(H @ Pp[i] @ H.T + R)
        x = xp[i] + K @ (points[i] - H @ xp[i])
        P = (np.eye(4) - K @ H) @ Pp[i]
        xf[i], Pf[i] = x, P
    xs = xf.copy()
    for i in range(n - 2, -1, -1):
        C = Pf[i] @ Fs[i + 1].T @ np.linalg.inv(Pp[i + 1])
        xs[i] = xf[i] + C @ (xs[i + 1] - xp[i + 1])
    return xs[:, :2]


def _segments(entries):
    """Split one track's (time, hand) entries at gaps and non-observed frames."""
    segment = []
    for time, hand in entries:
        if not hand["observed"] or hand.get("image_xyz_raw") is None:
            if segment:
                yield segment
            segment = []
            continue
        if segment and time - segment[-1][0] > GAP_S:
            yield segment
            segment = []
        segment.append((time, hand))
    if segment:
        yield segment


def smooth_samples(samples: list[dict], width: int, height: int) -> int:
    """Rewrite ``image_xyz`` / ``world_xyz_m`` of observed hands in place. Returns hands smoothed."""
    scale = np.array([width, height], float)
    by_track: dict[int, list] = {}
    for sample in samples:
        for hand in sample["hands"]:
            by_track.setdefault(hand["track_id"], []).append((sample["timestamp_s"], hand))
    count = 0
    for entries in by_track.values():
        for segment in _segments(entries):
            times = np.array([t for t, _ in segment])
            raw = np.array([h["image_xyz_raw"] for _, h in segment], float)          # (n, 21, 3) normalised
            px = raw[:, :, :2]*scale
            wrist = rts_wrist(times, px[:, 0])
            fingers = OneEuro(FINGER_MIN_CUTOFF, FINGER_BETA)
            world_raw = [h.get("world_xyz_m_raw") for _, h in segment]
            world_filter = OneEuro(FINGER_MIN_CUTOFF, FINGER_BETA*PX_PER_METRE)
            for k, (t, hand) in enumerate(segment):
                relative = fingers(px[k] - px[k, 0], t)
                image = raw[k].copy()
                image[:, :2] = (relative + wrist[k])/scale
                hand["image_xyz"] = image.tolist()
                if world_raw[k] is not None:
                    w = np.asarray(world_raw[k], float)
                    hand["world_xyz_m"] = (world_filter(w - w[0], t) + w[0]).tolist()
                count += 1
    return count
