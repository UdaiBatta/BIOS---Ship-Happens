"""Validate per-frame JSONL records against egohand_twin_frame.schema.json (JSON Schema 2020-12).

The schema file is shipped unchanged inside the package (``egohand_twin/schemas``).
Validation is offline and reports error counts grouped by location and message,
plus the first few failing frame indices, so a broken field is traceable to frames.
"""
from __future__ import annotations

from collections import Counter
from importlib import resources
import json
from pathlib import Path
import re

from jsonschema import Draft202012Validator

SCHEMA_NAME = "egohand_twin_frame.schema.json"


def load_schema(path: Path | None = None) -> dict:
    if path is not None:
        schema = json.loads(Path(path).read_text())
    else:
        schema = json.loads(resources.files("egohand_twin").joinpath("schemas", SCHEMA_NAME).read_text())
    Draft202012Validator.check_schema(schema)
    return schema


def validate_jsonl(path: Path, schema: dict | None = None, max_examples: int = 5) -> dict:
    validator = Draft202012Validator(schema or load_schema())
    errors: Counter = Counter()
    examples: list[dict] = []
    frames = invalid_frames = 0
    with Path(path).open() as f:
        for line in f:
            record = json.loads(line)
            frames += 1
            found = list(validator.iter_errors(record))
            if not found:
                continue
            invalid_frames += 1
            for error in found:
                location = re.sub(r"\[\d+\]", "[*]", error.json_path)
                errors[(location, error.message if len(error.message) < 160 else error.message[:157]+"...")] += 1
                if len(examples) < max_examples:
                    examples.append({"frame_index": record.get("frame_index"), "path": error.json_path,
                                     "message": error.message[:200]})
    return {"file": str(path), "schema": SCHEMA_NAME, "frames": frames, "invalid_frames": invalid_frames,
            "valid": invalid_frames == 0,
            "errors": [{"location": loc, "message": msg, "count": n} for (loc, msg), n in errors.most_common()],
            "examples": examples}
