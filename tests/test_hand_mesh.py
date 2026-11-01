"""The viewer's generated hand surface (frontend/prototype/hand-mesh.js), run with Node."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess

import numpy as np
import pytest

MESH_JS = Path(__file__).resolve().parents[1]/"frontend"/"prototype"/"hand-mesh.js"


def synthetic_hand(mirror: bool = False) -> list:
    """A plausible open hand in camera metres, about 0.4 m in front of the camera."""
    joints = np.zeros((21, 3))
    joints[0] = [0, .05, .40]
    knuckles = {1: -.03, 5: -.025, 9: -.005, 13: .014, 17: .03}
    for base, x in knuckles.items():
        reach = .035 if base == 1 else .09
        start = joints[0] + [x, -reach, .0]
        for k in range(4 if base == 1 else 4):
            joints[base + k] = start + [x*.3*k, -.025*k, .004*k]
    if mirror:
        joints[:, 0] *= -1
    return joints.tolist()


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js not installed")
def test_every_part_is_closed_and_wound_outward_for_left_and_right_hands():
    script = f"""
const M = require({json.dumps(str(MESH_JS))});
const hands = {json.dumps([synthetic_hand(False), synthetic_hand(True)])};
const out = hands.map((j) => {{ const v = M.build(j); return {{ n: v.length / 3, vols: M.partVolumes(v), finite: v.every(Number.isFinite) }}; }});
const set = M.forHands([{{ frame_index: 3, track_id: 1, joints: hands[0] }}, {{ frame_index: 3, track_id: 2, joints: [[0, 0]] }}]);
console.log(JSON.stringify({{ out, nv: M.VERTEX_COUNT, faces: M.FACES.length, maxFace: Math.max(...M.FACES), records: set.records.length }}));
"""
    result = json.loads(subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True).stdout)
    assert result["faces"] % 3 == 0 and result["maxFace"] < result["nv"]
    for hand in result["out"]:
        assert hand["n"] == result["nv"] and hand["finite"]
        assert all(v > 0 for v in hand["vols"])  # each capsule and the palm wound outward
    assert result["records"] == 1  # invalid joints are skipped, not drawn


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js not installed")
def test_bone_lengths_are_calibrated_per_track():
    rng = np.random.default_rng(0)
    base = np.array(synthetic_hand(False))
    frames = [(base + rng.normal(0, .004, base.shape)).tolist() for _ in range(15)]   # noisy, stretching bones
    script = f"""
const M = require({json.dumps(str(MESH_JS))});
const frames = {json.dumps(frames)};
const L = M.boneLengths(frames);
const P = [-1,0,1,2,3,0,5,6,7,0,9,10,11,0,13,14,15,0,17,18,19];
const len = (a, b) => Math.hypot(a[0]-b[0], a[1]-b[1], a[2]-b[2]);
const raw = frames.map((j) => len(j[8], j[7])), cal = frames.map((j) => {{ const c = M.calibrate(j, L); return len(c[8], c[7]); }});
const sd = (a) => {{ const m = a.reduce((x, y) => x + y) / a.length; return Math.sqrt(a.reduce((x, y) => x + (y - m) ** 2, 0) / a.length); }};
const c0 = M.calibrate(frames[0], L);
const dirOk = [1,5,8,12].every((i) => {{ const a = [0,1,2].map((k) => frames[0][i][k] - frames[0][P[i]][k]), b = [0,1,2].map((k) => c0[i][k] - c0[P[i]][k]);
  const na = Math.hypot(...a), nb = Math.hypot(...b); return (a[0]*b[0] + a[1]*b[1] + a[2]*b[2]) / (na * nb) > 0.999; }});
const set = M.forHands(frames.map((j, i) => ({{ frame_index: i, track_id: 7, joints: j }})));
console.log(JSON.stringify({{ rawSd: sd(raw), calSd: sd(cal), dirOk, records: set.records.length }}));
"""
    r = json.loads(subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True).stdout)
    assert r["rawSd"] > 1e-3 and r["calSd"] < 1e-9           # index distal bone: varies raw, constant calibrated
    assert r["dirOk"] and r["records"] == 15                  # directions kept; every frame meshed


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js not installed")
def test_posture_mesh_profile_ignores_invalid_samples_and_preserves_measurements():
    script = f"""
const M = require({json.dumps(str(MESH_JS))});
const joints = {json.dumps(synthetic_hand())};
const before = JSON.stringify(joints);
const profile = M.profile([joints, [[NaN, 0, 0]]]);
const vertices = M.build(M.calibrate(joints, profile.lengths), profile.scale);
console.log(JSON.stringify({{ same: JSON.stringify(joints) === before,
  finite: vertices.every(Number.isFinite), vertices: vertices.length / 3,
  empty: M.profile([]), lengths: profile.lengths.length }}));
"""
    result = json.loads(subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True).stdout)
    assert result["same"] and result["finite"]
    assert result["vertices"] == 970 and result["lengths"] == 21
    assert result["empty"] is None
