"""Candidate privacy flags (RUN/privacy_flags.json): frames that MAY show a face, for human review.

Review assistance only, never a guarantee: a missed face is possible (small, side-on, blurred or
behind the fisheye edge) and so is a false alarm. Only FACES are flagged: screens, documents and
other identifying details are not detected (no validated detector for them on this footage).

Method: MediaPipe Face Detector (BlazeFace short range, Apache-2.0, SHA-256-pinned) on one frame
per ``every_s`` seconds of the run interval, on the 960 px inference frame. Each flag records the
time, frame, normalised box, detector score, category, source and review status.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import urllib.request

import numpy as np

FACE_MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/"
                  "float16/1/blaze_face_short_range.tflite")
FACE_MODEL_SHA256 = "b4578f35940bf5a1a655214a1cce5cab13eba73c1297cd78e1a04c2380b0152f"


def fetch_face_model(path: Path) -> Path:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".download")
        with urllib.request.urlopen(FACE_MODEL_URL, timeout=90) as r:
            tmp.write_bytes(r.read())
        digest = hashlib.sha256(tmp.read_bytes()).hexdigest()
        if digest != FACE_MODEL_SHA256:
            tmp.unlink(missing_ok=True)
            raise ValueError(f"face model SHA-256 mismatch ({digest})")
        tmp.replace(path)
    return path


def scan_privacy(video: Path, run: Path, model: Path, every_s: float = 1., min_score: float = .5,
                 max_width: int = 960) -> dict:
    import cv2
    import mediapipe as mp
    manifest = json.loads((run/"manifest.json").read_text())
    times = []
    with (run/"landmarks.jsonl").open() as f:
        for line in f:
            r = json.loads(line)
            times.append((r["frame_index"], r["timestamp_s"]))
    wanted, next_t = {}, None
    for index, t in times:
        if next_t is None or t >= next_t:
            wanted[index] = t
            next_t = t + every_s
    options = mp.tasks.vision.FaceDetectorOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=str(model)), min_detection_confidence=min_score)
    flags = []
    with mp.tasks.vision.FaceDetector.create_from_options(options) as detector:
        cap = cv2.VideoCapture(str(video))
        index, last = -1, max(wanted) if wanted else -1
        try:
            while index < last:
                if index + 1 in wanted:
                    ok, frame = cap.read()
                else:
                    ok, frame = cap.grab(), None
                if not ok:
                    break
                index += 1
                if index not in wanted:
                    continue
                h, w = frame.shape[:2]
                scale = min(1., max_width/w)
                small = cv2.resize(frame, (round(w*scale), round(h*scale))) if scale < 1 else frame
                rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
                result = detector.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb)))
                sh, sw = rgb.shape[:2]
                for d in result.detections:
                    b = d.bounding_box
                    flags.append({"flag_id": f"pf{len(flags):05d}", "timestamp_s": round(wanted[index], 4), "frame_index": index,
                                  "box_xywh_norm": [round(b.origin_x/sw, 4), round(b.origin_y/sh, 4), round(b.width/sw, 4), round(b.height/sh, 4)],
                                  "score": round(float(d.categories[0].score), 3), "category": "face_candidate",
                                  "source": "mediapipe_blazeface_short_range", "review_status": "unreviewed"})
        finally:
            cap.release()
    return {"schema": "egohand_privacy_flags/0.1", "video_sha256": manifest.get("source", {}).get("sha256"),
            "frames_checked": len(wanted), "every_s": every_s, "min_score": min_score, "flags": flags,
            "categories_checked": ["face_candidate"],
            "not_checked": ["screens", "documents", "badges", "other identifying details"],
            "note": "Review assistance only: misses and false alarms are possible; not a privacy certification."}


def write_privacy(video: Path, run: Path, model: Path, every_s: float = 1.) -> Path:
    out = run/"privacy_flags.json"
    out.write_text(json.dumps(scan_privacy(video, run, model, every_s), indent=1) + "\n")
    return out
