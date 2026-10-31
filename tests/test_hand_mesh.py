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
