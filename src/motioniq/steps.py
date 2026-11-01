"""Step markers for teach-back review, stored in a sidecar ``steps.json`` next to a run.

A reviewer marks procedure steps on the replay timeline. The sidecar never changes
hand data; it only adds human-authored labels.

File format (version "1"):

```json
{
  "steps_version": "1",
  "source_sha256": "<from the run manifest>",
  "run_id": "<first 12 hex of the run manifest SHA-256>",
  "time_base": "timestamp_s of landmarks.jsonl: seconds from the first source presentation timestamp",
  "steps": [
    {"start_s": 1.0, "end_s": 6.0, "label": "Wipe slab", "version": 1,
     "note": "Cloth in right hand", "reviewer": "initials", "signed_off": false}
  ]
}
```

Rules enforced by :func:`validate_steps`:
- times are finite seconds on the run's time base, ``start_s < end_s``, inside the processed interval;
- ``label`` is a non-empty string; ``version`` is a positive integer;
- ``signed_off`` is a boolean, and ``signed_off=true`` requires a non-empty ``reviewer``;
- the sidecar must belong to the same source and run.

Steps describe what a person says happens; they are not detected by the system and
make no claim about contact, force, grasp quality, product quality or performance.
Do not put worker names or productivity scores in labels or notes.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

STEPS_VERSION = "1"
REQUIRED = ("start_s", "end_s", "label", "version", "note", "reviewer", "signed_off")


def run_identity(run: Path) -> tuple[str, str, tuple[float, float]]:
    """(source_sha256, run_id, (first_timestamp_s, last_timestamp_s)) for a completed run."""
    if not (run/"COMPLETE").exists():
        raise ValueError("Run is incomplete")
    manifest_bytes = (run/"manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    first = last = None
    with (run/"landmarks.jsonl").open() as f:
        for line in f:
            t = json.loads(line)["timestamp_s"]
            first = t if first is None else first
            last = t
    if first is None:
        raise ValueError("Run has no frames")
    return manifest["source"]["sha256"], hashlib.sha256(manifest_bytes).hexdigest()[:12], (first, last)


def template(run: Path) -> dict:
    source, run_id, _ = run_identity(run)
    return {"steps_version": STEPS_VERSION, "source_sha256": source, "run_id": run_id,
            "time_base": "timestamp_s of landmarks.jsonl: seconds from the first source presentation timestamp",
            "steps": []}


def validate_steps(data: dict, run: Path) -> list[dict]:
    """Return the steps sorted by start time, or raise ValueError naming the first problem."""
    source, run_id, (first, last) = run_identity(run)
    if str(data.get("steps_version")) != STEPS_VERSION:
        raise ValueError(f"steps_version must be {STEPS_VERSION!r}")
    if data.get("source_sha256") != source:
        raise ValueError("steps.json belongs to a different source video")
    if data.get("run_id") != run_id:
        raise ValueError("steps.json belongs to a different processing run")
    steps = data.get("steps")
    if not isinstance(steps, list):
        raise ValueError("steps must be a list")
    for i, step in enumerate(steps):
        where = f"step {i}"
        missing = [k for k in REQUIRED if k not in step]
        if missing:
            raise ValueError(f"{where}: missing fields {missing}")
        for key in ("start_s", "end_s"):
            value = step[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"{where}: {key} must be a finite number of seconds")
        if not step["start_s"] < step["end_s"]:
            raise ValueError(f"{where}: start_s must be before end_s")
        if step["start_s"] < first - 1e-6 or step["end_s"] > last + 1. + 1e-6:
            raise ValueError(f"{where}: outside the processed interval {first:.3f}-{last:.3f} s")
        if not isinstance(step["label"], str) or not step["label"].strip():
            raise ValueError(f"{where}: label must be a non-empty string")
        if isinstance(step["version"], bool) or not isinstance(step["version"], int) or step["version"] < 1:
            raise ValueError(f"{where}: version must be a positive integer")
        if not isinstance(step["note"], str):
            raise ValueError(f"{where}: note must be a string (may be empty)")
        if not isinstance(step["signed_off"], bool):
            raise ValueError(f"{where}: signed_off must be true or false")
        if step["reviewer"] is not None and not isinstance(step["reviewer"], str):
            raise ValueError(f"{where}: reviewer must be a string or null")
        if step["signed_off"] and not (step["reviewer"] or "").strip():
            raise ValueError(f"{where}: signed_off=true requires a reviewer")
    return sorted(steps, key=lambda s: (s["start_s"], s["end_s"]))


def load_steps(path: Path, run: Path) -> list[dict]:
    return validate_steps(json.loads(path.read_text()), run)


def write_template(run: Path, out: Path) -> Path:
    if out.exists():
        raise ValueError("steps file exists; choose a new filename (never overwritten)")
    out.write_text(json.dumps(template(run), indent=2)+"\n")
    return out
