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


def map_crop_detection(d: Detection, box, width, height, origin="center_crop_rescue") -> Detection:
    """Restore normalized image coordinates; a crop does not rotate local 3D axes.

    ``box`` and ``width``/``height`` must be in the pixel units of the image the
    crop was cut from (downscaled inference frame or full-resolution source).
    MediaPipe image z is in roughly crop-width units, so it is rescaled by the
    crop's fraction of the full width. World (metric, hand-relative) landmarks are
    unchanged because cropping neither rotates nor rescales the hand.
    """
    x0, y0, x1, y1 = box
    image = d.image.copy()
    image[:, 0] = (image[:, 0]*(x1-x0)+x0)/width
    image[:, 1] = (image[:, 1]*(y1-y0)+y0)/height
    image[:, 2] *= (x1-x0)/width
    return Detection(image, d.world.copy(), d.side, d.handedness_score, d.index, origin)


def wrist_distance(a: Detection, b: Detection, width: int, height: int) -> float:
    """Wrist distance in image-diagonal units (aspect-ratio correct)."""
    scale = np.array([width, height])/np.hypot(width, height)
    return float(np.linalg.norm((a.image[0, :2]-b.image[0, :2])*scale))


def hand_scale_px(d: Detection, width: int, height: int) -> float:
    xy = d.image[:, :2]*[width, height]
    return float(max(np.ptp(xy[:, 0]), np.ptp(xy[:, 1]), 1.))


def is_duplicate(a: Detection, b: Detection, width: int, height: int,
                 policy: str = "landmarks") -> bool:
    """Decide whether two estimates describe the same physical hand.

    ``wrist`` reproduces the original rule (wrist within 0.10 in anisotropic
    normalized x/y units), which can merge two real hands that are side by side.
    ``landmarks`` compares all 21 points in pixels relative to hand size: two
    estimates of one hand agree point-by-point, whereas two adjacent or crossing
    hands differ in pose and position even when their wrists are close.
    """
    if policy == "wrist":
        return bool(np.linalg.norm(a.image[0, :2]-b.image[0, :2]) < .10)
    pa, pb = a.image[:, :2]*[width, height], b.image[:, :2]*[width, height]
    mean = float(np.mean(np.linalg.norm(pa-pb, axis=1)))
    scale = max(hand_scale_px(a, width, height), hand_scale_px(b, width, height))
    return mean < .35*scale


def square_box(cx, cy, side, width, height):
    """Integer square crop clamped inside the image (shrinks only if the image is smaller)."""
    side = int(round(min(side, width, height)))
    x0 = int(round(min(max(cx-side/2, 0), width-side)))
    y0 = int(round(min(max(cy-side/2, 0), height-side)))
    return x0, y0, x0+side, y0+side


def tile_boxes(width, height, count=3, fraction=.75):
    """Overlapping squares spanning the full width, covering y >= (1-fraction)*height."""
    side = int(round(height*fraction))
    if count == 1:
        xs = [(width-side)//2]
    else:
        xs = [round(i*(width-side)/(count-1)) for i in range(count)]
    return [(x, height-side, x+side, height) for x in xs]


class CropRescueDetector:
    """Optional extra center crop when full-frame detection returns too few hands.

    Historical experiment: the crop is cut from the downscaled inference frame and
    duplicates are suppressed with the original wrist rule. Kept unchanged for
    reproducibility; see MultiViewDetector for the full-resolution variants.
    """
    def __init__(self, *args, **kwargs):
        self.primary = Detector(*args, **kwargs)
        secondary_options = {**kwargs, "mode": "image"}
        self.secondary = Detector(*args, **secondary_options)
        self.num_hands = kwargs.get("num_hands", 2)
        self.stats = {"crops": 0}

    def detect(self, rgb, timestamp_s, full_bgr=None):
        detections = self.primary.detect(rgb, timestamp_s)
        if len(detections) >= self.num_hands:
            return detections
        height, width = rgb.shape[:2]
        box = (width//4, height//4, 3*width//4, height)
        x0, y0, x1, y1 = box
        self.stats["crops"] += 1
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


class MultiViewDetector:
    """Full-frame VIDEO-mode detection plus bounded full-resolution crop proposals.

    Strategies (applied only while fewer than ``num_hands`` hands are found):

    - ``guided``: a square around each recently seen hand that the current frame
      missed. A memory entry is *anchored* only by a non-guided detection (full
      frame, center or tile). Guided detections refresh position but never the
      anchor, so after ``guided_anchor_s`` without independent confirmation the
      entry expires: a false positive cannot keep confirming itself.
    - ``center``: the original center/lower crop, cut from the full-resolution frame.
    - ``tiles``: overlapping squares across the full width of the lower region.

    Crops are run through an independent IMAGE-mode landmarker. At most
    ``max_crops`` crops are evaluated per frame. Earlier sources take precedence
    when duplicates are found; handedness scores are never used to choose between
    duplicate estimates because they do not measure landmark accuracy.
    """
    def __init__(self, model_path, strategies=("center",), max_crops=4, dedupe="landmarks",
                 guided_scale=2.5, guided_min_px=320, guided_gap_s=.5, guided_anchor_s=1.,
                 guided_gate=.08, tile_count=3, tile_fraction=.75, crop_max_side=None, **kwargs):
        unknown = set(strategies) - {"guided", "center", "tiles"}
        if unknown:
            raise ValueError(f"Unknown rescue strategies: {sorted(unknown)}")
        self.primary = Detector(model_path, **kwargs)
        self.secondary = Detector(model_path, **{**kwargs, "mode": "image"})
        self.num_hands = kwargs.get("num_hands", 2)
        self.strategies = [s for s in ("guided", "center", "tiles") if s in strategies]
        self.max_crops, self.dedupe = max_crops, dedupe
        self.guided_scale, self.guided_min_px = guided_scale, guided_min_px
        self.guided_gap_s, self.guided_anchor_s, self.guided_gate = guided_gap_s, guided_anchor_s, guided_gate
        self.tile_count, self.tile_fraction = tile_count, tile_fraction
        # Optional area-filtered downscale of each crop before inference. Normalized
        # crop coordinates are resolution independent, so mapping is unchanged.
        self.crop_max_side = crop_max_side
        self.memory: list[dict] = []
        self.stats = {"crops": 0, "frames_with_crops": 0, "accepted": {}, "duplicates": 0,
                      "guided_rejected_gate": 0, "memory_expired": 0}

    def _boxes(self, width, height, detections, timestamp_s):
        boxes = []
        if "guided" in self.strategies:
            for entry in self.memory:
                if any(wrist_distance(entry["detection"], d, width, height) < self.guided_gate
                       for d in detections):
                    continue
                xy = entry["detection"].image[:, :2]*[width, height]
                side = max(hand_scale_px(entry["detection"], width, height)*self.guided_scale,
                           self.guided_min_px)
                boxes.append(("guided_crop", square_box(*xy.mean(axis=0), side, width, height), entry))
        if "center" in self.strategies:
            boxes.append(("center_crop_full", (width//4, height//4, 3*width//4, height), None))
        if "tiles" in self.strategies:
            boxes += [(f"tile_{i}", b, None) for i, b in
                      enumerate(tile_boxes(width, height, self.tile_count, self.tile_fraction))]
        return boxes[:self.max_crops]

    def detect(self, rgb, timestamp_s, full_bgr=None):
        self._prune(timestamp_s)
        detections = self.primary.detect(rgb, timestamp_s)
        full = full_bgr if full_bgr is not None else rgb[:, :, ::-1]
        height, width = full.shape[:2]
        if len(detections) < self.num_hands and self.strategies:
            boxes = self._boxes(width, height, detections, timestamp_s)
            self.stats["frames_with_crops"] += bool(boxes)
            for origin, box, entry in boxes:
                if len(detections) >= self.num_hands:
                    break
                x0, y0, x1, y1 = box
                crop = np.ascontiguousarray(full[y0:y1, x0:x1, ::-1]) if full_bgr is not None \
                    else np.ascontiguousarray(rgb[y0:y1, x0:x1])
                longest = max(crop.shape[:2])
                if self.crop_max_side and longest > self.crop_max_side:
                    import cv2
                    factor = self.crop_max_side/longest
                    crop = cv2.resize(crop, (max(1, round(crop.shape[1]*factor)), max(1, round(crop.shape[0]*factor))),
                                      interpolation=cv2.INTER_AREA)
                self.stats["crops"] += 1
                for candidate in self.secondary.detect(crop, timestamp_s):
                    candidate = map_crop_detection(candidate, box, width, height, origin)
                    if entry is not None and wrist_distance(
                            candidate, entry["detection"], width, height) > self.guided_gate:
                        self.stats["guided_rejected_gate"] += 1
                        continue
                    if any(is_duplicate(candidate, d, width, height, self.dedupe) for d in detections):
                        self.stats["duplicates"] += 1
                        continue
                    candidate.index = len(detections)
                    detections.append(candidate)
                    key = origin.split("_")[0] if origin.startswith("tile") else origin
                    self.stats["accepted"][key] = self.stats["accepted"].get(key, 0) + 1
                    if len(detections) >= self.num_hands:
                        break
        self._remember(detections, timestamp_s, width, height)
        return detections

    def _remember(self, detections, now, width, height):
        if "guided" not in self.strategies:
            return
        used = set()
        for d in detections:
            best, best_distance = None, self.guided_gate
            for k, entry in enumerate(self.memory):
                distance = wrist_distance(d, entry["detection"], width, height)
                if k not in used and distance < best_distance:
                    best, best_distance = k, distance
            if best is None:
                if d.origin != "guided_crop":
                    self.memory.append({"detection": d, "last": now, "anchor": now})
                    used.add(len(self.memory)-1)
                continue
            used.add(best)
            entry = self.memory[best]
            entry["detection"], entry["last"] = d, now
            if d.origin != "guided_crop":
                entry["anchor"] = now
        self._prune(now)
        self.memory = self.memory[-2*self.num_hands:]

    def _prune(self, now):
        kept = [e for e in self.memory if now-e["last"] <= self.guided_gap_s
                and now-e["anchor"] <= self.guided_anchor_s]
        self.stats["memory_expired"] += len(self.memory)-len(kept)
        self.memory = kept

    def close(self):
        self.primary.close()
        self.secondary.close()
