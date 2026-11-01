import argparse
from datetime import date
import json
from pathlib import Path

import pytest

from motioniq.governance import load, not_recorded, retention_report, template, validate
from motioniq.pipeline import process

TODAY = date(2026, 10, 31)


def good(**over):
    data = template()
    data.update({"purpose": "PS4 evaluation", "consent_status": "covered_by_organizer_terms",
                 "retention_until": "2026-11-02", "redaction_status": "none"})
    data.update(over)
    return data


def test_valid_file_copied_with_explicit_self_declaration():
    out = validate(good(), TODAY)
    assert out["governance"]["status"] == "recorded"
    assert "not verified" in out["governance"]["verification"]
    assert out["capture"]["intrinsics_source"] == "none"
    assert "experimental" in out["capture"]["geometry_validity"]


def test_missing_file_is_not_recorded_not_consent():
    out = load(None)
    assert out == not_recorded()
    assert out["governance"]["status"] == "not_recorded"


@pytest.mark.parametrize("over,message", [
    ({"worker_name": "A"}, "personal data"),
    ({"purpose": " "}, "purpose"),
    ({"consent_status": "yes"}, "consent_status"),
    ({"data_source": "own_recording", "consent_status": "pending"}, "written_consent"),
    ({"access": "public"}, "cannot be marked public"),
    ({"retention_until": "2026-10-01"}, "already past"),
    ({"retention_until": "next week"}, "ISO date"),
])
def test_invalid_governance_rejected(over, message):
    with pytest.raises(ValueError, match=message):
        validate(good(**over), TODAY)


def test_lens_source_rules():
    calibrated = good()
    calibrated["capture"] = {**calibrated["capture"], "intrinsics_source": "checkerboard"}
    with pytest.raises(ValueError, match="requires intrinsics"):
        validate(calibrated, TODAY)
    calibrated["capture"]["intrinsics"] = {"fx": 700., "fy": 700., "cx": 960., "cy": -1}
    with pytest.raises(ValueError, match="cy"):
        validate(calibrated, TODAY)
    calibrated["capture"]["intrinsics"]["cy"] = 540.
    with pytest.raises(ValueError, match="calibration_version"):
        validate(calibrated, TODAY)
    calibrated["capture"]["calibration_version"] = "cb-2026-10-31"
    assert validate(calibrated, TODAY)["capture"]["geometry_validity"] == "calibrated intrinsics declared"
    stray = good()
    stray["capture"] = {**stray["capture"], "intrinsics": {"fx": 1.}}
    with pytest.raises(ValueError, match="intrinsics=null"):
        validate(stray, TODAY)


def test_retention_report_never_deletes(tmp_path):
    def run(name, governance):
        d = tmp_path/name
        d.mkdir()
        (d/"COMPLETE").touch()
        manifest = {"source": {"name": "clip.mp4"}}
        if governance:
            manifest["governance"] = governance
        (d/"manifest.json").write_text(json.dumps(manifest))
        return d
    run("old", None)
    run("expired", {"status": "recorded", "retention_until": "2026-10-01"})
    run("ok", {"status": "recorded", "retention_until": "2026-11-02"})
    run("open", {"status": "recorded", "retention_until": None})
    rows = {Path(r["run"]).name: r["status"] for r in retention_report(tmp_path, TODAY)}
    assert rows == {"old": "governance_not_recorded", "expired": "past_retention_review_deletion",
                    "ok": "within_retention", "open": "no_retention_date"}
    assert all((tmp_path/n/"manifest.json").exists() for n in rows)


def test_process_fails_before_decoding_on_invalid_governance(tmp_path):
    video = tmp_path/"not_a_video.mp4"
    video.write_bytes(b"x")
    model = tmp_path/"m.task"
    model.write_bytes(b"x")
    bad = tmp_path/"g.json"
    bad.write_text(json.dumps(good(worker_name="A")))
    args = argparse.Namespace(video=str(video), out=str(tmp_path/"out"), model=str(model),
                              governance=str(bad))
    with pytest.raises(ValueError, match="personal data"):
        process(args)
    assert not (tmp_path/"out").exists()
