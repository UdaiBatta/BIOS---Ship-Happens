from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import urllib.request

import numpy as np

MODEL_URL = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
CONNECTIONS = [(0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6),
               (6, 7), (7, 8), (5, 9), (9, 10), (10, 11), (11, 12),
               (9, 13), (13, 14), (14, 15), (15, 16), (13, 17),
               (0, 17), (17, 18), (18, 19), (19, 20)]
COORDINATES = {
    "image_xyz": "x/width, y/height; z is wrist-relative depth in roughly x units",
    "world_xyz_m": "MediaPipe estimated meters, origin at each hand's geometric center",
    "display_xyz_m": "world coordinates minus wrist; display offsets are arbitrary",
    "absolute_hand_translation": "unavailable",
    "camera_pose": "unavailable",
    "handedness_score": "classifier score for left/right; NOT landmark confidence",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch_model(path: Path) -> dict:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".download")
        try:
            with urllib.request.urlopen(MODEL_URL, timeout=90) as r, temporary.open("wb") as f:
                while chunk := r.read(1024 * 1024):
                    f.write(chunk)
            # The official task bundle is a ZIP, not an HTML response.
            import zipfile
            if not zipfile.is_zipfile(temporary):
                raise ValueError("Downloaded model is not a task bundle")
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
    return {"url": MODEL_URL, "sha256": sha256(path), "bytes": path.stat().st_size}


@dataclass
class Detection:
    image: np.ndarray
    world: np.ndarray
    side: str
    handedness_score: float
    index: int = 0
    origin: str = "full_frame"

    def __post_init__(self):
        self.image = np.asarray(self.image, dtype=np.float64)
        self.world = np.asarray(self.world, dtype=np.float64)
        if self.image.shape != (21, 3) or self.world.shape != (21, 3):
            raise ValueError("A hand must contain 21 image and 21 world xyz landmarks")
        if not np.isfinite(self.image).all() or not np.isfinite(self.world).all():
            raise ValueError("Non-finite hand landmarks")


class Detector:
    def __init__(self, model_path: Path, detection: float = .5, presence: float = .5,
                 tracking: float = .5, mode: str = "video", num_hands: int = 2):
        import mediapipe as mp
        self.mp = mp
        self.mode = mode
        options = mp.tasks.vision.HandLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=str(model_path),
                                             delegate=mp.tasks.BaseOptions.Delegate.CPU),
            running_mode=(mp.tasks.vision.RunningMode.VIDEO if mode == "video"
                          else mp.tasks.vision.RunningMode.IMAGE),
            num_hands=num_hands,
            min_hand_detection_confidence=detection,
            min_hand_presence_confidence=presence,
            min_tracking_confidence=tracking,
        )
        self.task = mp.tasks.vision.HandLandmarker.create_from_options(options)
        self.last_ms = -1

    def detect(self, rgb: np.ndarray, timestamp_s: float) -> list[Detection]:
        image = self.mp.Image(image_format=self.mp.ImageFormat.SRGB,
                              data=np.ascontiguousarray(rgb))
        # API requires increasing integer milliseconds; retain full source PTS in export.
        ms = max(self.last_ms + 1, round(timestamp_s * 1000))
        self.last_ms = ms
        result = (self.task.detect_for_video(image, ms) if self.mode == "video"
                  else self.task.detect(image))
        detections = []
        for i, (image_lm, world_lm, categories) in enumerate(zip(
                result.hand_landmarks, result.hand_world_landmarks, result.handedness)):
            category = categories[0]
            detections.append(Detection(
                [[p.x, p.y, p.z] for p in image_lm],
                [[p.x, p.y, p.z] for p in world_lm],
                category.category_name, float(category.score), i))
        return detections

    def close(self):
        self.task.close()


def map_crop_detection(d: Detection, box, width, height) -> Detection:
    """Restore normalized image coordinates; a crop does not rotate local 3D axes."""
    x0, y0, x1, y1 = box
    image = d.image.copy()
    image[:, 0] = (image[:, 0]*(x1-x0)+x0)/width
    image[:, 1] = (image[:, 1]*(y1-y0)+y0)/height
    image[:, 2] *= (x1-x0)/width
    return Detection(image, d.world.copy(), d.side, d.handedness_score,
                     d.index, "center_crop_rescue")


class CropRescueDetector:
    """Optional extra center crop when full-frame detection returns too few hands."""
    def __init__(self, *args, **kwargs):
        self.primary = Detector(*args, **kwargs)
        secondary_options = {**kwargs, "mode": "image"}
        self.secondary = Detector(*args, **secondary_options)
        self.num_hands = kwargs.get("num_hands", 2)

    def detect(self, rgb, timestamp_s):
        detections = self.primary.detect(rgb, timestamp_s)
        if len(detections) >= self.num_hands:
            return detections
        height, width = rgb.shape[:2]
        box = (width//4, height//4, 3*width//4, height)
        x0, y0, x1, y1 = box
        for candidate in self.secondary.detect(rgb[y0:y1, x0:x1], timestamp_s):
            candidate = map_crop_detection(candidate, box, width, height)
            # Conservative duplicate suppression. Primary estimates take precedence.
            if any(np.linalg.norm(candidate.image[0, :2]-d.image[0, :2]) < .10
                   for d in detections):
                continue
            candidate.index = len(detections)
            detections.append(candidate)
            if len(detections) == self.num_hands:
                break
        return detections

    def close(self):
        self.primary.close()
        self.secondary.close()

