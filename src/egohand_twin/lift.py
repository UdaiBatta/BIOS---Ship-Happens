"""EXPERIMENTAL camera-space lifting of MediaPipe hands under an ASSUMED fisheye lens.

What this does
--------------
For each *observed* hand, MediaPipe provides 21 image landmarks (normalized x/y)
and 21 hand-relative metric landmarks (``world_xyz_m_raw``, origin near the hand's
geometric center). Given a camera model, a Perspective-n-Point fit finds the
rotation R and translation t such that ``R @ world + t`` projects onto the image
landmarks. ``t`` is then an estimate of the hand center in camera coordinates.

What it does NOT establish
--------------------------
- The official footage has no calibration. The lens model here is an assumed
  equidistant fisheye (r = f * theta) with the principal point at the image
  center and an assumed horizontal field of view. Depth scales roughly linearly
  with the assumed focal length; ``lift`` therefore reports a FOV sweep.
- Metric depth also inherits MediaPipe's learned hand size: a hand 10% larger
  than the model assumes appears 10% farther away.
- Low reprojection error is what PnP minimizes; it is a consistency check, not
  independent evidence that depth is correct.
- Coordinates are camera coordinates (x right, y down, z forward), not a fixed
  factory/world frame. Camera motion is not compensated.

Results are stored separately (``lift_<tag>.npz`` / ``lift_<tag>.json``); the raw
2D/3D arrays in landmarks.jsonl are untouched.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import cv2
import numpy as np

from .model import CONNECTIONS

LIFT_SCHEMA_VERSION = "0.1-experimental"
MAX_THETA = math.radians(85.)  # rays at/after 90 degrees cannot be expressed as pinhole points


class EquidistantFisheye:
    """r = f * theta, principal point (cx, cy), square pixels, no extra distortion terms."""
    def __init__(self, width: int, height: int, hfov_deg: float):
        if not 10 < hfov_deg < 240:
            raise ValueError("hfov_deg must be between 10 and 240")
        self.width, self.height, self.hfov_deg = width, height, hfov_deg
        self.f = (width/2)/math.radians(hfov_deg/2)
        self.cx, self.cy = width/2, height/2

    def describe(self) -> dict:
        return {"model": "equidistant_fisheye", "status": "ASSUMED (not calibrated)",
                "hfov_deg": self.hfov_deg, "f_px": self.f, "cx": self.cx, "cy": self.cy,
                "width": self.width, "height": self.height}

    def pixels_to_normalized(self, px: np.ndarray):
        """Pixel coords -> ideal pinhole coords (x/z, y/z) and a validity mask."""
        d = px - [self.cx, self.cy]
        r = np.linalg.norm(d, axis=1)
        theta = r/self.f
        valid = theta < MAX_THETA
        with np.errstate(invalid="ignore", divide="ignore"):
            scale = np.where(r > 1e-9, np.tan(theta)/r, 1./self.f)
        return d*scale[:, None], valid

    def project(self, points: np.ndarray) -> np.ndarray:
        x, y, z = points[:, 0], points[:, 1], points[:, 2]
        rho = np.hypot(x, y)
        theta = np.arctan2(rho, z)
        with np.errstate(invalid="ignore", divide="ignore"):
            scale = np.where(rho > 1e-12, self.f*theta/rho, self.f/np.maximum(z, 1e-12))
        return np.stack([self.cx + x*scale, self.cy + y*scale], axis=1)


def solve_hand(camera: EquidistantFisheye, image_xy_norm: np.ndarray, world_m: np.ndarray,
               max_reproj_px: float = 25., min_depth_m: float = .05, max_depth_m: float = 5.):
    """PnP for one hand. Returns a dict; ``ok`` is False with a reason on rejection.

    Non-finite results, negative/implausibly small depth, too few valid rays and
    large reprojection residuals are rejected rather than clamped.
    """
    px = np.asarray(image_xy_norm, float)*[camera.width, camera.height]
    world = np.asarray(world_m, float)
    normalized, valid = camera.pixels_to_normalized(px)
    if valid.sum() < 6:
        return {"ok": False, "reason": "too_few_rays_inside_85deg"}
    obj, img = world[valid].astype(np.float64), normalized[valid].astype(np.float64)
    spread = np.linalg.svd(img - img.mean(axis=0), compute_uv=False)
    if spread[0] <= 0 or spread[1]/spread[0] < .08:
        # Near-collinear image landmarks: PnP can return a low-residual but arbitrary pose.
        return {"ok": False, "reason": "degenerate_2d_configuration"}
    ok, rvec, tvec = cv2.solvePnP(obj, img, np.eye(3), None, flags=cv2.SOLVEPNP_SQPNP)
    if not ok or not np.all(np.isfinite(rvec)) or not np.all(np.isfinite(tvec)):
        return {"ok": False, "reason": "pnp_failed"}
    rvec, tvec = cv2.solvePnPRefineLM(obj, img, np.eye(3), None, rvec, tvec)
    R, _ = cv2.Rodrigues(rvec)
    cam = world @ R.T + tvec.ravel()
    if np.any(cam[:, 2] <= 0):
        return {"ok": False, "reason": "point_behind_camera"}
    depth = float(tvec[2, 0])
    residual = np.linalg.norm(camera.project(cam) - px, axis=1)
    out = {"t_cam_m": tvec.ravel().tolist(), "rvec": rvec.ravel().tolist(),
           "rotation_from_identity_deg": float(np.degrees(np.linalg.norm(rvec))),
           "joints_cam_m": cam.tolist(), "reproj_rmse_px": float(np.sqrt(np.mean(residual**2))),
           "reproj_max_px": float(residual.max()), "valid_rays": int(valid.sum())}
    if not (min_depth_m <= depth <= max_depth_m):
        return {**out, "ok": False, "reason": "depth_outside_solver_limits"}
    if out["reproj_rmse_px"] > max_reproj_px:
        return {**out, "ok": False, "reason": "reprojection_rmse_too_large"}
    return {**out, "ok": True, "reason": None}


def bone_lengths(points: np.ndarray) -> np.ndarray:
    c = np.asarray(CONNECTIONS)
    return np.linalg.norm(points[c[:, 0]] - points[c[:, 1]], axis=1)


def lift_run(run: Path, hfov_deg: float, tag: str | None = None, max_reproj_px: float = 25.) -> dict:
    if not (run/"COMPLETE").exists():
        raise ValueError("Run is incomplete")
    tag = tag or f"hfov{int(round(hfov_deg))}"
    arrays_path, summary_path = run/f"lift_{tag}.npz", run/f"lift_{tag}.json"
    if arrays_path.exists() or summary_path.exists():
        raise ValueError(f"lift_{tag} output exists; never overwritten")
    manifest = json.loads((run/"manifest.json").read_text())
    camera = EquidistantFisheye(int(manifest["source"]["width"]), int(manifest["source"]["height"]), hfov_deg)
    rows, reasons = [], {}
    with (run/"landmarks.jsonl").open() as f:
        for line in f:
            frame = json.loads(line)
            for hand in frame["hands"]:
                if not hand["observed"]:
                    continue  # predicted/lost tracks have no observed 3D
                result = solve_hand(camera, np.asarray(hand["image_xyz_raw"])[:, :2],
                                    hand["world_xyz_m_raw"], max_reproj_px)
                reasons[result["reason"] or "ok"] = reasons.get(result["reason"] or "ok", 0) + 1
                rows.append((frame["frame_index"], frame["timestamp_s"], hand["track_id"], result))
    ok = [r for r in rows if r[3]["ok"]]
    n = len(rows)
    shape = (n, 21, 3)
    joints = np.full(shape, np.nan, np.float32)
    root = np.full((n, 3), np.nan, np.float32)
    rmse = np.full(n, np.nan, np.float32)
    for i, (_, _, _, r) in enumerate(rows):
        if r["ok"]:
            joints[i], root[i], rmse[i] = r["joints_cam_m"], r["t_cam_m"], r["reproj_rmse_px"]
    np.savez_compressed(arrays_path, joints_cam_m=joints, hand_center_cam_m=root,
                        reproj_rmse_px=rmse,
                        frame_index=np.array([r[0] for r in rows], np.int64),
                        timestamp_s=np.array([r[1] for r in rows]),
                        track_id=np.array([r[2] for r in rows], np.int64),
                        ok=np.array([r[3]["ok"] for r in rows], bool))
    depth = np.array([r[3]["t_cam_m"][2] for r in ok]) if ok else np.array([])
    wrist_depth = np.array([r[3]["joints_cam_m"][0][2] for r in ok]) if ok else np.array([])
    rot = np.array([r[3]["rotation_from_identity_deg"] for r in ok]) if ok else np.array([])
    err = np.array([r[3]["reproj_rmse_px"] for r in ok]) if ok else np.array([])

    def q(a):
        return ({"n": int(a.size), "p05": float(np.percentile(a, 5)), "median": float(np.median(a)),
                 "p95": float(np.percentile(a, 95))} if a.size else {"n": 0})
    # Inter-hand distance only where two hands were lifted in the same frame.
    by_frame: dict[int, list] = {}
    for r in ok:
        by_frame.setdefault(r[0], []).append(np.asarray(r[3]["t_cam_m"]))
    inter = np.array([np.linalg.norm(v[0]-v[1]) for v in by_frame.values() if len(v) == 2])
    summary = {
        "schema_version": LIFT_SCHEMA_VERSION, "status": "EXPERIMENTAL - assumed lens, unvalidated depth",
        "camera": camera.describe(),
        "declared_capture": manifest.get("capture") or {"status": "not_recorded (pre-0.4 run)"},
        "observed_hands": n, "lifted": len(ok), "rejections": reasons,
        "hand_center_depth_m": q(depth), "wrist_depth_m": q(wrist_depth),
        "fraction_wrist_depth_0p2_0p9m": float(np.mean((wrist_depth >= .2) & (wrist_depth <= .9))) if wrist_depth.size else None,
        "reprojection_rmse_px": q(err),
        "pnp_rotation_from_identity_deg": q(rot),
        "inter_hand_center_distance_m": q(inter),
        "notes": ["Depth scales with the assumed focal length and MediaPipe's hand-size prior.",
                  "Reprojection error is minimized by PnP and is not independent depth validation.",
                  "0.2-0.9 m is a heuristic sanity band, not a correctness criterion.",
                  "Camera coordinates only; no factory/world frame or camera motion compensation."],
    }
    summary_path.write_text(json.dumps(summary, indent=2)+"\n")
    return summary


def hand_relative_variation(run: Path) -> dict:
    """Bone-length coefficient of variation per track for raw MediaPipe world landmarks."""
    per_track: dict[int, list] = {}
    with (run/"landmarks.jsonl").open() as f:
        for line in f:
            for hand in json.loads(line)["hands"]:
                if hand["observed"]:
                    per_track.setdefault(hand["track_id"], []).append(bone_lengths(np.asarray(hand["world_xyz_m_raw"])))
    cvs = []
    for lengths in per_track.values():
        if len(lengths) >= 5:
            a = np.asarray(lengths)
            cvs.append(np.std(a, axis=0)/np.mean(a, axis=0))
    if not cvs:
        return {"tracks": 0}
    cvs = np.asarray(cvs)
    return {"tracks_with_5plus_observations": int(len(cvs)),
            "median_bone_cv": float(np.median(cvs)), "p90_bone_cv": float(np.percentile(cvs, 90)),
            "note": "Raw MediaPipe world landmarks; no bone-length calibration applied."}
