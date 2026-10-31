import hashlib
import json
from types import SimpleNamespace

import pytest

from egohand_twin.cli import identity_command
from egohand_twin.identity import write_identity


def run_with_landmarks(tmp_path):
    (tmp_path/"COMPLETE").touch()
    rows = []
    for i in range(3):
        rows.append({"frame_index": i, "timestamp_s": i/30, "hands": [{
            "track_id": 4, "observed": True, "raw_side": "Left", "handedness_score": .9,
        }]})
    raw = "\n".join(json.dumps(row) for row in rows) + "\n"
    (tmp_path/"landmarks.jsonl").write_bytes(raw.encode())
    return raw.encode()


def test_identity_binds_vote_to_exact_landmarks_bytes(tmp_path):
    raw = run_with_landmarks(tmp_path)
    output = write_identity(tmp_path)
    assert json.loads(output.read_text())["landmarks_sha256"] == hashlib.sha256(raw).hexdigest()


def test_identity_cli_preflights_both_outputs_before_writing(tmp_path):
    run_with_landmarks(tmp_path)
    sidecar = tmp_path/"landmarks.identity.jsonl"
    sidecar.write_bytes(b"keep these bytes\n")
    with pytest.raises(ValueError, match="never overwritten"):
        identity_command(SimpleNamespace(run=str(tmp_path), write_jsonl=True, margin=.15, min_observed=3))
    assert not (tmp_path/"identity.json").exists()
    assert sidecar.read_bytes() == b"keep these bytes\n"
