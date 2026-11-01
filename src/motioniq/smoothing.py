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
  to metres (about 1200 px per metre for a hand on this footage). Finger-bone directions use
  adjacent observed frames without lag; bone lengths are smoothed separately before reconstruction.

Segments are one track's consecutive observed frames. A gap over 0.2 s or any non-observed frame
ends the segment, so nothing is smoothed across a loss or between different tracks. Raw values
(`image_xyz_raw`, `world_xyz_m_raw`) are never modified. Image z (relative depth) is left raw.

Holdout: wrist error median 26.6 px (raw 25.3, old 45.3), wrist jitter 16.2 -> 8.1 px,
fingertip jitter 21.9 -> 12.7 px, fast-motion offset from raw 65 -> 6 px.
"""
from __future__ import annotations

import numpy as np

from .model import CONNECTIONS
from .tracking import OneEuro

GAP_S = .2
WRIST_Q = 4000.     # px/s^2: Kalman process noise (acceleration) for the wrist
WRIST_R = 4.        # px: measurement noise
FINGER_MIN_CUTOFF, FINGER_BETA = 1., .05      # Hz, per px/s
PX_PER_METRE = 1200.
# Palm joints keep their filtered positions; only finger chains are reconstructed.
WORLD_FINGER_BONES = [edge for edge in CONNECTIONS if edge[1] not in (5, 9, 13, 17)]


def _center_bone_directions(previous: np.ndarray, current: np.ndarray, following: np.ndarray,
                            fraction: float) -> np.ndarray:
    """Blend current directions with the time-aligned directions between its neighbors."""
    dot = np.clip(np.sum(previous*following, axis=1), -1., 1.)
    angle = np.arccos(dot)
    sine = np.sin(angle)
    neighbor = previous*(1 - fraction) + following*fraction
    valid = (np.linalg.norm(previous, axis=1) > .5) & (np.linalg.norm(following, axis=1) > .5)
    curved = valid & (sine > 1e-5)
    neighbor[curved] = (previous[curved]*np.sin((1 - fraction)*angle[curved])[:, None]
                        + following[curved]*np.sin(fraction*angle[curved])[:, None])/sine[curved, None]
    neighbor[~valid | ((dot < 0) & ~curved)] = current[~valid | ((dot < 0) & ~curved)]
    return (current + neighbor)/2


def _restore_world_bones(filtered: np.ndarray, lengths: np.ndarray, directions: np.ndarray,
                         raw_directions: np.ndarray) -> np.ndarray:
    """Keep filtered palm joints and independently smoothed finger lengths/directions."""
    result = filtered.copy()
    for length_index, (parent, child) in enumerate(WORLD_FINGER_BONES):
        direction = directions[length_index]
        length = np.linalg.norm(direction)
        if length < 1e-9:
            direction = raw_directions[length_index]
            length = np.linalg.norm(direction)
        if length < 1e-9:
            direction = filtered[child] - filtered[parent]
            length = np.linalg.norm(direction)
        if length >= 1e-9:
            result[child] = result[parent] + direction * (lengths[length_index] / length)
    return result


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
            world_raw = [np.asarray(h["world_xyz_m_raw"], float) if h.get("world_xyz_m_raw") is not None
                         else None for _, h in segment]
            world_filter = OneEuro(FINGER_MIN_CUTOFF, FINGER_BETA*PX_PER_METRE)
            # Anatomical length does not speed up when a detection jumps.
            bone_filter = OneEuro(FINGER_MIN_CUTOFF, 0.)
            bone_a, bone_b = np.asarray(WORLD_FINGER_BONES).T
            bone_vectors = [w[bone_b] - w[bone_a] if w is not None else None for w in world_raw]
            bone_lengths = [np.linalg.norm(v, axis=1) if v is not None else None for v in bone_vectors]
            bone_units = [v / np.maximum(length[:, None], 1e-9) if v is not None else None
                          for v, length in zip(bone_vectors, bone_lengths)]
            for k, (t, hand) in enumerate(segment):
                relative = fingers(px[k] - px[k, 0], t)
                image = raw[k].copy()
                image[:, :2] = (relative + wrist[k])/scale
                hand["image_xyz"] = image.tolist()
                if world_raw[k] is not None:
                    w = world_raw[k]
                    filtered = world_filter(w - w[0], t) + w[0]
                    lengths = bone_filter(bone_lengths[k], t)
                    directions = bone_units[k]
                    if (0 < k < len(segment) - 1 and bone_units[k - 1] is not None
                            and bone_units[k + 1] is not None and times[k - 1] < t < times[k + 1]):
                        fraction = (t - times[k - 1])/(times[k + 1] - times[k - 1])
                        directions = _center_bone_directions(bone_units[k - 1], directions,
                                                             bone_units[k + 1], fraction)
                    hand["world_xyz_m"] = _restore_world_bones(filtered, lengths, directions, bone_units[k]).tolist()
                count += 1
    return count
