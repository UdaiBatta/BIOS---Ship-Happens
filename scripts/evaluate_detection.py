"""Detection metrics for one or more runs: recall, precision, F1, false positives, per-category recall.

Usage:  uv run python scripts/evaluate_detection.py LABELS.json RUN:SPLIT [RUN:SPLIT ...]

Wraps `egohand evaluate` (same matching rule: raw observed wrists within 0.10 image diagonals;
predicted tracks never count). Per-category recall uses the label tags; tags overlap, so the
categories must not be summed. Labels are provisional until reviewed.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

from egohand_twin.evaluation import evaluate


def detection_metrics(run: str, labels: str, split: str | None) -> dict:
    result = evaluate(Path(run), Path(labels), allow_provisional=True, split=split)
    groups = result["recall_by_group"]
    k, n = groups["all"]["recall"]["k"], groups["all"]["recall"]["n"]
    precision = result["precision"]
    recall = k/n if n else None
    f1 = 2*precision*recall/(precision + recall) if precision and recall else None
    tags = {g.split("=", 1)[1]: f'{v["matched"]}/{v["labeled_hands"]}' for g, v in groups.items()
            if g.startswith("tag=") or g.startswith("visibility=")}
    return {"run": run, "split": split, "recall": f"{k}/{n}", "recall_value": recall,
            "precision": precision, "f1": f1, "false_positives": result["false_positives"],
            "by_category": tags, "label_status": result.get("label_status")}


def main(argv):
    for spec in argv[1:]:
        run, _, split = spec.partition(":")
        print(json.dumps(detection_metrics(run, argv[0], split or None)))


if __name__ == "__main__":
    main(sys.argv[1:])
