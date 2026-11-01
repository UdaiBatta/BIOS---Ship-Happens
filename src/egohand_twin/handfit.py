"""Hand-relative 3D for hands that only RTMPose could read (2D points, no 3D).

MediaPipe gives every hand it reads a hand-relative 3D shape; RTMPose gives only 2D. To
place such a hand in 3D (and draw its mesh), this module builds a 3D shape that keeps the
detected 2D points exactly and borrows only the depth:

1. a rigid fit (rotation, scale, offset; weak perspective) of the median MediaPipe hand to
   the 21 points, trying both hand sides and both palm directions (towards / away from the
   camera); the lowest error wins;
2. x and y of every joint come from the detected points (converted to metres with the
   fitted scale); z comes from the fitted median hand.

The median hand is the median of 1274 MediaPipe hand-relative 3D hands from this project's
runs (palm frame: wrist at the origin, +y towards the middle knuckle, +z the side the
fingers curl towards; a left hand is its mirror image).

Measured against MediaPipe's own 3D on 120 MediaPipe hands (whose 2D points were fed in):
median joint distance 17.4 mm after rigid alignment (a rigid median hand: 18.6 mm; the
median hand with the side known: 13.5 mm). A jointed-finger fit was tried first and was
worse (17.7 mm) and slower. MediaPipe's 3D is itself an estimate, so this is agreement, not
accuracy. A 2D-only shape cannot see finger depth: a finger bent towards or away from the
camera looks the same, and the depth follows the typical hand.
Output: metres, camera orientation, origin at the hand's geometric centre (MediaPipe world
convention), marked ``rtmpose_fitted_3d`` by the caller.
"""
from __future__ import annotations

import numpy as np

MEDIAN_HAND = np.array([
    [0., 0., 0.], [.0202, .0264, .0098], [.0253, .0506, .0218], [.0279, .0771, .0281], [.0256, .0962, .0308],
    [.0143, .0872, 0.], [.0113, .1052, .0083], [.0053, .113, .0227], [.0017, .1176, .0346],
    [0., .0844, -.003], [-.0056, .1067, .0078], [-.0084, .1117, .0224], [-.0122, .1174, .0386],
    [-.0123, .0799, -.0032], [-.0173, .0933, .0071], [-.0234, .0973, .0212], [-.0245, .1004, .0344],
    [-.0224, .0631, 0.], [-.0271, .0753, .0075], [-.0316, .0817, .0188], [-.0318, .0861, .0253]])


def _rotation(v: np.ndarray) -> np.ndarray:
    angle = float(np.linalg.norm(v))
    if angle < 1e-12:
        return np.eye(3)
    a = v/angle
    k = np.array([[0, -a[2], a[1]], [a[2], 0, -a[0]], [-a[1], a[0], 0]])
    return np.eye(3) + np.sin(angle)*k + (1 - np.cos(angle))*(k @ k)


def _initial_rotation(points2d: np.ndarray, palm_away: bool) -> np.ndarray:
    """Rotation vector putting the hand's +y along the 2D wrist->middle-knuckle direction and
    its palm normal towards (or away from) the camera."""
    from scipy.spatial.transform import Rotation
    up = np.array([*(points2d[9] - points2d[0]), 0.])
    up = up/np.linalg.norm(up) if np.linalg.norm(up) > 1e-9 else np.array([0., -1., 0.])
    normal = np.array([0., 0., 1. if palm_away else -1.])
    return Rotation.from_matrix(np.stack([np.cross(up, normal), up, normal], 1)).as_rotvec()


def fit_hand(points2d: np.ndarray, scores: np.ndarray | None = None, max_rms: float = .12):
    """21x3 hand-relative metres for 21 pixel points, or None when no plausible hand fits.

    ``max_rms``: allowed RMS distance between the rigid median hand and the points, relative to
    the hand's size (rejects keypoint sets that do not look like a hand at all).
    """
    from scipy.optimize import least_squares
    points2d = np.asarray(points2d, float)
    if points2d.shape != (21, 2) or not np.isfinite(points2d).all():
        return None
    weights = (np.ones(21) if scores is None else np.clip(np.asarray(scores, float), .05, 1.))[:, None]
    size = float(np.linalg.norm(points2d.max(0) - points2d.min(0)))
    if size < 4:
        return None
    best = None
    for mirror in (False, True):
        hand = MEDIAN_HAND*([1, 1, -1] if mirror else 1)
        for palm_away in (False, True):
            def residuals(p, hand=hand):
                return ((p[3]*(hand @ _rotation(p[:3]).T)[:, :2] + p[4:6] - points2d)/size*weights).ravel()
            p0 = np.concatenate([_initial_rotation(points2d, palm_away), [size/.17], points2d.mean(0)])
            r = least_squares(residuals, p0, max_nfev=60)
            if best is None or r.cost < best[0]:
                best = (r.cost, hand, r.x)
    cost, hand, p = best
    if not p[3] > 0 or np.sqrt(2*cost/21) > max_rms:
        return None
    out = np.zeros((21, 3))
    out[:, :2] = (points2d - p[4:6])/p[3]
    out[:, 2] = (hand @ _rotation(p[:3]).T)[:, 2]
    return out - out.mean(0)
