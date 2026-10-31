"""Capture conditions and evaluation exclusions, stored in a sidecar ``conditions.json``.

Conditions describe the FOOTAGE, not a processing run, so the sidecar is bound to the
source video hash and can be used to evaluate any run of that source. Times use the
pipeline time base: seconds since the first presentation timestamp of the source file
(``timestamp_s`` in landmarks.jsonl), which is identical across runs of the same file.

```json
{
  "conditions_version": "1",
  "source_sha256": "<source hash>",
  "time_base": "seconds since the first source presentation timestamp",
  "intervals": [
    {"start_s": 0.0, "end_s": 12.0, "glove_ppe": "none", "occlusion": "partial",
     "lighting": "ok", "excluded": false, "exclusion_reason": null,
     "reviewer": null, "note": "cloth in right hand"}
  ]
}
```

Values: glove_ppe/occlusion in {none, partial, heavy, unknown}; lighting in
{ok, dark, harsh, unknown}. Intervals must not overlap (one condition set per frame).
``excluded=true`` removes a frame from evaluation and requires an ``exclusion_reason``;
excluded frames are still counted and reported, never silently dropped.

These are human annotations (or a single annotator's provisional reading). They are
not measured by the software and say nothing about worker performance.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

CONDITIONS_VERSION = "1"
LEVELS = {"none", "partial", "heavy", "unknown"}
LIGHTING = {"ok", "dark", "harsh", "unknown"}
REQUIRED = ("start_s", "end_s", "glove_ppe", "occlusion", "lighting", "excluded",
            "exclusion_reason", "reviewer", "note")


def validate_conditions(data: dict, source_sha256: str) -> list[dict]:
    """Return intervals sorted by start time, or raise ValueError naming the first problem."""
    if str(data.get("conditions_version")) != CONDITIONS_VERSION:
        raise ValueError(f"conditions_version must be {CONDITIONS_VERSION!r}")
    if data.get("source_sha256") != source_sha256:
        raise ValueError("conditions.json belongs to a different source video")
    intervals = data.get("intervals")
    if not isinstance(intervals, list):
        raise ValueError("intervals must be a list")
    for i, item in enumerate(intervals):
        where = f"interval {i}"
        missing = [k for k in REQUIRED if k not in item]
        if missing:
            raise ValueError(f"{where}: missing fields {missing}")
        unknown = set(item) - set(REQUIRED)
        if unknown:
            raise ValueError(f"{where}: unknown fields {sorted(unknown)} (no personal data fields)")
        for key in ("start_s", "end_s"):
            v = item[key]
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0:
                raise ValueError(f"{where}: {key} must be a finite, non-negative number of seconds")
        if not item["start_s"] < item["end_s"]:
            raise ValueError(f"{where}: start_s must be before end_s")
        for key in ("glove_ppe", "occlusion"):
            if item[key] not in LEVELS:
                raise ValueError(f"{where}: {key} must be one of {sorted(LEVELS)}")
        if item["lighting"] not in LIGHTING:
            raise ValueError(f"{where}: lighting must be one of {sorted(LIGHTING)}")
        if not isinstance(item["excluded"], bool):
            raise ValueError(f"{where}: excluded must be true or false")
        reason = item["exclusion_reason"]
        if item["excluded"] and not (isinstance(reason, str) and reason.strip()):
            raise ValueError(f"{where}: excluded=true requires an exclusion_reason")
        if not item["excluded"] and reason not in (None, ""):
            raise ValueError(f"{where}: exclusion_reason given but excluded=false")
        if item["reviewer"] is not None and not isinstance(item["reviewer"], str):
            raise ValueError(f"{where}: reviewer must be a string or null")
        if not isinstance(item["note"], str):
            raise ValueError(f"{where}: note must be a string")
    ordered = sorted(intervals, key=lambda x: x["start_s"])
    for a, b in zip(ordered, ordered[1:]):
        if b["start_s"] < a["end_s"]:
            raise ValueError(f"intervals overlap: {a['start_s']}-{a['end_s']} and {b['start_s']}-{b['end_s']}")
    return ordered


def load_conditions(path: Path, source_sha256: str) -> list[dict]:
    return validate_conditions(json.loads(Path(path).read_text()), source_sha256)


def condition_at(intervals: list[dict], timestamp_s: float) -> dict | None:
    """Interval containing ``timestamp_s`` (start inclusive, end exclusive), or None."""
    for item in intervals:
        if item["start_s"] <= timestamp_s < item["end_s"]:
            return item
    return None


def apply_conditions(run: Path, conditions: Path, source_file: str = "landmarks.jsonl") -> Path:
    """Write RUN/<stem>.conditions.jsonl with frame quality.conditions/excluded fields.

    Frames outside every interval get conditions "unknown" and excluded=false. The input
    JSONL is never modified and the output is never overwritten.
    """
    manifest = json.loads((run/"manifest.json").read_text())
    intervals = load_conditions(conditions, manifest["source"]["sha256"])
    source = run/source_file
    out = run/(Path(source_file).stem + ".conditions.jsonl")
    if out.exists():
        raise ValueError(f"{out.name} exists; never overwritten")
    with source.open() as fin, out.open("w") as fout:
        for line in fin:
            frame = json.loads(line)
            item = condition_at(intervals, frame["timestamp_s"])
            quality = frame.setdefault("quality", {})
            quality["conditions"] = ({k: item[k] for k in ("glove_ppe", "occlusion", "lighting")} if item
                                     else {"glove_ppe": "unknown", "occlusion": "unknown", "lighting": "unknown"})
            quality["excluded"] = bool(item and item["excluded"])
            quality["exclusion_reason"] = item["exclusion_reason"] if item and item["excluded"] else None
            quality["conditions_source"] = "human annotation (conditions.json)" if item else "not annotated"
            fout.write(json.dumps(frame, separators=(",", ":"), allow_nan=False)+"\n")
    return out


def template(source_sha256: str) -> dict:
    return {"conditions_version": CONDITIONS_VERSION, "source_sha256": source_sha256,
            "time_base": "seconds since the first source presentation timestamp", "intervals": []}
