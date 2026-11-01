"""Compare temporal 3D stability with identical raw observations; this does not measure accuracy."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from egohand_twin.smoothing import WORLD_FINGER_BONES


def load(run: Path) -> tuple[list, dict]:
    frames = [json.loads(line) for line in (run/"landmarks.jsonl").read_text().splitlines() if line.strip()]
    hands = {(f["frame_index"], h["track_id"]): h for f in frames for h in f["hands"]
             if h["observed"] and h.get("world_xyz_m_raw") is not None}
    return frames, hands


def compare(reference: Path, candidate: Path) -> dict:
    old_frames, old = load(reference)
    new_frames, new = load(candidate)
    if not old or old.keys() != new.keys() or [(f["frame_index"], f["timestamp_s"]) for f in old_frames] != [(f["frame_index"], f["timestamp_s"]) for f in new_frames]:
        raise ValueError("Runs must contain the same frames and observed tracks")
    if any(old[key][field] != new[key][field] for key in old for field in ("image_xyz_raw", "world_xyz_m_raw")):
        raise ValueError("Raw observations differ; this comparison cannot isolate smoothing")
    timestamps = {f["frame_index"]: f["timestamp_s"] for f in new_frames}
    triples = [[(f+d, track) for d in (-1, 0, 1)] for f, track in old
               if all((f+d, track) in old for d in (-1, 0, 1))
               and 0 < timestamps[f]-timestamps[f-1] <= .2 and 0 < timestamps[f+1]-timestamps[f] <= .2]
    if not triples:
        raise ValueError("No consecutive observed-hand triples to compare")
    parent, child = np.asarray(WORLD_FINGER_BONES).T
    result = {"metric": "Unit finger-direction second difference; temporal stability, not accuracy",
              "frames": len(new_frames), "observed_hand_samples": len(new), "identical_raw_samples": len(new),
              "consecutive_hand_triples": len(triples)}
    for label, hands in (("before", old), ("after", new)):
        angles, distances = [], []
        for keys in triples:
            units = []
            for key in keys:
                points = np.asarray(hands[key]["world_xyz_m"], float)
                vectors = points[child]-points[parent]
                units.append(vectors/np.maximum(np.linalg.norm(vectors, axis=1)[:, None], 1e-9))
            valid = np.all([np.linalg.norm(u, axis=1) > .5 for u in units], axis=0)
            angles.extend(np.linalg.norm(units[2][valid]-2*units[1][valid]+units[0][valid], axis=1))
        for hand in hands.values():
            distances.extend(np.linalg.norm(np.asarray(hand["world_xyz_m"])[1:]-np.asarray(hand["world_xyz_m_raw"])[1:], axis=1)*1000)
        if not angles:
            raise ValueError("No valid finger directions to compare")
        result[label] = dict(zip(("p50", "p90", "p99"), map(float, np.quantile(angles, [.5, .9, .99]))))
        result[label]["distance_from_raw_mm"] = dict(zip(("p50", "p90", "p99"), map(float, np.quantile(distances, [.5, .9, .99]))))
        result[label]["finger_bone_samples"] = len(angles)
    result["joint_distance_samples"] = len(distances)
    before = result["before"]["p90"]
    result["p90_reduction_percent"] = 100*(before-result["after"]["p90"])/before if before else None
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference", type=Path)
    parser.add_argument("candidate", type=Path)
    args = parser.parse_args()
    try:
        result = compare(args.reference, args.candidate)
    except (OSError, ValueError, KeyError) as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
