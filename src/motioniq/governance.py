"""Governance and capture/lens provenance recorded in each run's manifest.json.

A governance file is validated before any processing starts and copied into
``manifest["governance"]`` and ``manifest["capture"]``. When none is given, the
manifest says so explicitly (``status: not_recorded``) instead of implying consent.

Example ``governance.json`` (all keys shown; unknown keys are rejected so that
personal data such as worker names cannot slip in):

```json
{
  "purpose": "PS4 hackathon evaluation of hand-motion reconstruction",
  "data_source": "organizer_provided",
  "consent_status": "covered_by_organizer_terms",
  "retention_until": "2026-11-02",
  "redaction_status": "none",
  "access": "private_team_only",
  "notes": "",
  "capture": {
    "device": "unknown head-mounted camera",
    "camera_placement": "head-mounted",
    "lens_model": "unknown",
    "intrinsics": null,
    "intrinsics_source": "none",
    "calibration_version": null
  }
}
```

``intrinsics`` (pixels): ``{"fx", "fy", "cx", "cy"}`` plus optional ``"distortion"`` (list),
in the source image's pixel coordinates (x right, y down). They are required when
``intrinsics_source`` is ``organizers``, ``checkerboard`` or ``plumb_line``, and must
be null for ``none``. ``assumed_fov`` is not a calibration: geometry derived from it
stays experimental.

This module records statements made by people; it cannot verify consent or redaction.
"""
from __future__ import annotations

from datetime import date
import json
import math
from pathlib import Path

GOVERNANCE_VERSION = "1"
ENUMS = {
    "data_source": {"organizer_provided", "own_recording", "other"},
    "consent_status": {"covered_by_organizer_terms", "written_consent_obtained", "pending", "unknown"},
    "redaction_status": {"none", "partial", "complete", "unknown"},
    "access": {"private_team_only", "private_with_judges", "public"},
}
CAPTURE_ENUMS = {
    "camera_placement": {"head-mounted", "chest-mounted", "fixed", "unknown"},
    "intrinsics_source": {"none", "organizers", "checkerboard", "plumb_line", "assumed_fov"},
}
TOP_KEYS = {"purpose", "data_source", "consent_status", "retention_until", "redaction_status", "access",
            "notes", "capture"}
CAPTURE_KEYS = {"device", "camera_placement", "lens_model", "intrinsics", "intrinsics_source",
                "calibration_version"}
CALIBRATED_SOURCES = {"organizers", "checkerboard", "plumb_line"}


def not_recorded() -> dict:
    return {"governance": {"version": GOVERNANCE_VERSION, "status": "not_recorded",
                           "note": "No governance file was given. Consent, retention and redaction are UNKNOWN; "
                                   "treat the run as restricted."},
            "capture": {"lens_model": "unknown", "intrinsics": None, "intrinsics_source": "none",
                        "calibration_version": None, "status": "not_recorded"}}


def validate(data: dict, today: date | None = None) -> dict:
    """Validate a governance dict; return {"governance": ..., "capture": ...} for the manifest."""
    if not isinstance(data, dict):
        raise ValueError("Governance file must contain a JSON object")
    unknown = set(data) - TOP_KEYS
    if unknown:
        raise ValueError(f"Unknown governance keys {sorted(unknown)}; personal data fields are not accepted")
    missing = TOP_KEYS - set(data)
    if missing:
        raise ValueError(f"Missing governance keys {sorted(missing)}")
    if not isinstance(data["purpose"], str) or not data["purpose"].strip():
        raise ValueError("purpose must be a non-empty string")
    for key, allowed in ENUMS.items():
        if data[key] not in allowed:
            raise ValueError(f"{key} must be one of {sorted(allowed)}")
    if data["data_source"] == "own_recording" and data["consent_status"] != "written_consent_obtained":
        raise ValueError("own recordings require consent_status=written_consent_obtained")
    if data["access"] == "public" and data["data_source"] == "organizer_provided":
        raise ValueError("organizer-provided footage and derived outputs cannot be marked public")
    retention = data["retention_until"]
    if retention is not None:
        try:
            parsed = date.fromisoformat(retention)
        except (TypeError, ValueError):
            raise ValueError("retention_until must be an ISO date (YYYY-MM-DD) or null") from None
        if today is not None and parsed < today:
            raise ValueError(f"retention_until {retention} is already past; review deletion before processing")
    if not isinstance(data["notes"], str):
        raise ValueError("notes must be a string")
    capture = data["capture"]
    if not isinstance(capture, dict):
        raise ValueError("capture must be an object")
    unknown = set(capture) - CAPTURE_KEYS
    missing = CAPTURE_KEYS - set(capture)
    if unknown or missing:
        raise ValueError(f"capture keys: unknown {sorted(unknown)}, missing {sorted(missing)}")
    for key, allowed in CAPTURE_ENUMS.items():
        if capture[key] not in allowed:
            raise ValueError(f"capture.{key} must be one of {sorted(allowed)}")
    intrinsics, source = capture["intrinsics"], capture["intrinsics_source"]
    if source in CALIBRATED_SOURCES:
        if not isinstance(intrinsics, dict):
            raise ValueError(f"intrinsics_source={source} requires intrinsics {{fx, fy, cx, cy}}")
        for k in ("fx", "fy", "cx", "cy"):
            v = intrinsics.get(k)
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0:
                raise ValueError(f"intrinsics.{k} must be a positive number of pixels")
        if not capture["calibration_version"]:
            raise ValueError("calibrated intrinsics need a calibration_version")
    elif source == "none" and intrinsics is not None:
        raise ValueError("intrinsics_source=none must have intrinsics=null")
    governance = {k: data[k] for k in TOP_KEYS - {"capture"}}
    governance.update({"version": GOVERNANCE_VERSION, "status": "recorded",
                       "verification": "self-declared by the operator; not verified by the software"})
    return {"governance": governance,
            "capture": {**capture, "status": "recorded",
                        "geometry_validity": ("calibrated intrinsics declared" if source in CALIBRATED_SOURCES
                                              else "no calibrated intrinsics; any metric camera-space "
                                                   "geometry is experimental")}}


def load(path: Path | None, today: date | None = None) -> dict:
    if path is None:
        return not_recorded()
    return validate(json.loads(Path(path).read_text()), today)


def template() -> dict:
    return {"purpose": "", "data_source": "organizer_provided", "consent_status": "unknown",
            "retention_until": None, "redaction_status": "unknown", "access": "private_team_only", "notes": "",
            "capture": {"device": "unknown", "camera_placement": "unknown", "lens_model": "unknown",
                        "intrinsics": None, "intrinsics_source": "none", "calibration_version": None}}


def retention_report(root: Path, today: date) -> list[dict]:
    """List completed runs under ``root`` with their retention status. Never deletes anything."""
    rows = []
    for manifest_path in sorted(Path(root).rglob("manifest.json")):
        run = manifest_path.parent
        if not (run/"COMPLETE").exists():
            continue
        manifest = json.loads(manifest_path.read_text())
        gov = manifest.get("governance") or {"status": "not_recorded (pre-0.4 run)"}
        until = gov.get("retention_until")
        if gov.get("status") != "recorded":
            status = "governance_not_recorded"
        elif until is None:
            status = "no_retention_date"
        elif date.fromisoformat(until) < today:
            status = "past_retention_review_deletion"
        else:
            status = "within_retention"
        rows.append({"run": str(run), "source": manifest.get("source", {}).get("name"),
                     "retention_until": until, "consent_status": gov.get("consent_status"),
                     "access": gov.get("access"), "status": status})
    return rows
