"""Side-by-side table of detection and identity metrics for several runs of the same frames.

Usage:  uv run python scripts/compare_baseline.py LABELS.json SPLIT NAME=RUN [NAME=RUN ...]

Every run must cover the same interval; the first is the reference. Prints markdown.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from evaluate_detection import detection_metrics  # noqa: E402
from evaluate_identity import identity_metrics  # noqa: E402


def main(argv):
    labels_path, split, specs = argv[0], argv[1], argv[2:]
    labels = json.load(open(labels_path))
    print("| Config | Recall | Precision | F1 | FP | Side correct | Labelled flips | Side changes in tracks | Ghost frames | Detect s | FPS |")
    print("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for spec in specs:
        name, _, run = spec.partition("=")
        d, i = detection_metrics(run, labels_path, split), identity_metrics(run, labels, split)
        m = json.load(open(f"{run}/metrics.json"))
        detect = (m.get("parallel") or {}).get("detection_wall_seconds") or m["stage_seconds"]["detect"]
        print(f'| {name} | {d["recall"]} | {d["precision"]:.3f} | {d["f1"]:.3f} | {d["false_positives"]} | '
              f'{i["side_correct"]}/{i["side_matched"]} | {i["labelled_flips"]} | {i["side_changes_within_tracks"]} | '
              f'{i["ghost_frames"]} | {detect:.1f} | {m["end_to_end_fps"]:.1f} |')


if __name__ == "__main__":
    main(sys.argv[1:])
