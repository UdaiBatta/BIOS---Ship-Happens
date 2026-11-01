"""Privacy flags: pinned model, structured candidates, honest scope."""
import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from motioniq.privacy import FACE_MODEL_SHA256, scan_privacy

MODEL = Path(__file__).resolve().parents[1]/"models"/"blaze_face_short_range.tflite"


@pytest.mark.skipif(not MODEL.exists(), reason="face model not fetched (motioniq privacy fetches it)")
def test_blank_video_gives_no_flags_and_declares_scope(tmp_path):
    import hashlib
    assert hashlib.sha256(MODEL.read_bytes()).hexdigest() == FACE_MODEL_SHA256
    video = tmp_path/"v.avi"
    w = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"MJPG"), 10, (160, 90))
    for _ in range(25):
        w.write(np.full((90, 160, 3), 90, np.uint8))
    w.release()
    run = tmp_path/"run"; run.mkdir()
    (run/"manifest.json").write_text(json.dumps({"source": {"sha256": "x"}}))
    (run/"landmarks.jsonl").write_text("".join(json.dumps({"frame_index": i, "timestamp_s": i/10, "hands": []}) + "\n" for i in range(25)))
    out = scan_privacy(video, run, MODEL, every_s=1.)
    assert out["frames_checked"] == 3 and out["flags"] == []
    assert "screens" in out["not_checked"] and "not a privacy certification" in out["note"]
