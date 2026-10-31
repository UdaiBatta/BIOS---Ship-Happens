"""Hybrid hand detection: MediaPipe first, an RTMDet hand detector for the hands it misses.

Why: MediaPipe finds hands with a PALM detector. In head-camera factory footage palms are
often hidden (gripping tools, fists, cloth, side views, hands cut by the image edge), and
then MediaPipe never looks at the hand, even though its landmark model can often read it
from a good crop (the centre crop alone doubled recall). RTMDet-nano (hand) detects the
WHOLE hand as a box, so it proposes where to look.

Per frame, while fewer than ``num_hands`` hands are found:
1. RTMDet proposes hand boxes on the inference frame.
2. For each box that is not an already-found hand, MediaPipe (IMAGE mode) reads a square
   crop around it -> 21 points, MediaPipe's hand-relative 3D and left/right, exactly as for
   any other MediaPipe hand (origin ``hand_detector``, detail ``rtmdet_box``).
3. If MediaPipe still finds nothing in the crop, RTMPose-m (hand) gives the 21 2D points and
   ``handfit`` fits a jointed hand to them for the hand-relative 3D (detail
   ``rtmpose_fitted_3d``). Left/right stays neutral (score 0.5) for these: neither model
   provides it, and the track-level vote decides from the track's MediaPipe frames.

Models (Apache-2.0, OpenMMLab, ONNX; run with onnxruntime on CPU):
- rtmdet_nano_8xb32-300e_hand (input 320x320, BGR, mean/std in BGR order, NMS in the graph)
- rtmpose-m_simcc-hand5 (input 256x256, RGB, SimCC decoding, 21 points in MediaPipe order)
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import shutil
import urllib.request
import zipfile

import numpy as np

from .model import Detection, map_crop_detection

RTM_MODELS = {
    "rtmdet_nano_hand.onnx": {
        "url": "https://download.openmmlab.com/mmpose/v1/projects/rtmposev1/onnx_sdk/"
               "rtmdet_nano_8xb32-300e_hand-267f9c8f.zip",
        "zip_sha256": "9c0370a43c02b2fe42b4382aba7383d97cfa3ed35623b655cac4f0c25cfde402",
    },
    "rtmpose_m_hand.onnx": {
        "url": "https://download.openmmlab.com/mmpose/v1/projects/rtmposev1/onnx_sdk/"
               "rtmpose-m_simcc-hand5_pt-aic-coco_210e-256x256-74fb594_20230320.zip",
        "zip_sha256": "45c9e1aa21b8fe33859973c49bce4647645d312e7a226e398a42f9137d44a56d",
    },
}


def fetch_rtm_models(directory: Path, zips: Path | None = None) -> dict:
    """Download (or take from ``zips``) the two model archives, verify SHA-256, extract the ONNX."""
    directory.mkdir(parents=True, exist_ok=True)
    report = {}
    for name, info in RTM_MODELS.items():
        target = directory/name
        if not target.exists():
            archive = directory/(name + ".zip.download")
            try:
                source = zips/Path(info["url"]).name if zips else None
                if source is not None and source.exists():
                    shutil.copyfile(source, archive)
                else:
                    with urllib.request.urlopen(info["url"], timeout=120) as r, archive.open("wb") as f:
                        shutil.copyfileobj(r, f)
                digest = hashlib.sha256(archive.read_bytes()).hexdigest()
                if digest != info["zip_sha256"]:
                    raise ValueError(f"{name}: SHA-256 mismatch ({digest})")
                with zipfile.ZipFile(archive) as z:
                    member = next(m for m in z.namelist() if m.endswith("end2end.onnx"))
                    with z.open(member) as src, target.with_suffix(".part").open("wb") as dst:
                        shutil.copyfileobj(src, dst)
                target.with_suffix(".part").replace(target)
            finally:
                archive.unlink(missing_ok=True)
                target.with_suffix(".part").unlink(missing_ok=True)
        report[name] = {"bytes": target.stat().st_size,
                        "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                        "source": info["url"], "licence": "Apache-2.0 (OpenMMLab)"}
    return report


def _session(path: Path, threads: int):
    import onnxruntime as ort
    options = ort.SessionOptions()
    options.intra_op_num_threads = threads
    options.inter_op_num_threads = 1
    return ort.InferenceSession(str(path), options, providers=["CPUExecutionProvider"])


class RtmHand:
    """RTMDet-nano hand boxes and RTMPose-m hand keypoints (onnxruntime, CPU)."""
    DET_SIZE = 320
    POSE_SIZE = 256

    def __init__(self, directory: Path, box_threshold: float = .2, threads: int = 2, tiles: int = 4):
        missing = [n for n in RTM_MODELS if not (directory/n).exists()]
        if missing:
            raise FileNotFoundError(f"RTM hand models missing in {directory}: run 'egohand fetch-model --rtm'")
        self.det = _session(directory/"rtmdet_nano_hand.onnx", threads)
        self.pose = _session(directory/"rtmpose_m_hand.onnx", threads)
        self.box_threshold = box_threshold
        self.tiles = tiles

    def tiled_boxes(self, rgb: np.ndarray) -> list[tuple]:
        """Boxes from overlapping tiles (2x2 by default): the detector's input is only 320 px, so
        on a whole 960 px frame a hand is ~25 px tall. Measured on dev frames (provisional labels):
        a box at 43/72 labelled hands with 2x2 tiles vs 22/72 on the whole frame (score >= 0.2)."""
        h, w = rgb.shape[:2]
        if self.tiles <= 1:
            regions = [(0, 0, w, h)]
        else:
            tw, th = w//2 + w//8, h//2 + h//8
            regions = [(x, y, x + tw, y + th) for x in (0, w - tw) for y in (0, h - th)]
        out = []
        for x0, y0, x1, y1 in regions:
            out += [(a + x0, b + y0, c + x0, d + y0, s)
                    for a, b, c, d, s in self.boxes(np.ascontiguousarray(rgb[y0:y1, x0:x1]))]
        kept = []
        for box in sorted(out, key=lambda b: -b[4]):           # suppress duplicates across tiles
            if all(_overlap(box, k) < .5 for k in kept):
                kept.append(box)
        return kept

    def boxes(self, rgb: np.ndarray) -> list[tuple]:
        """Hand boxes (x0, y0, x1, y1, score) in the pixels of ``rgb``, best first."""
        import cv2
        h, w = rgb.shape[:2]
        ratio = min(self.DET_SIZE/h, self.DET_SIZE/w)
        resized = cv2.resize(rgb[:, :, ::-1], (int(w*ratio), int(h*ratio)), interpolation=cv2.INTER_LINEAR)
        padded = np.full((self.DET_SIZE, self.DET_SIZE, 3), 114, np.uint8)
        padded[:resized.shape[0], :resized.shape[1]] = resized
        x = (padded - np.array([103.53, 116.28, 123.675]))/np.array([57.375, 57.12, 58.395])  # BGR
        dets = self.det.run(None, {"input": x.transpose(2, 0, 1)[None].astype(np.float32)})[0][0]
        out = [(*(d[:4]/ratio).tolist(), float(d[4])) for d in dets if d[4] >= self.box_threshold]
        clipped = [(max(0., a), max(0., b), min(w, c), min(h, d), s) for a, b, c, d, s in out]
        return sorted([b for b in clipped if b[2] - b[0] > 4 and b[3] - b[1] > 4], key=lambda b: -b[4])

    def keypoints(self, rgb: np.ndarray, box) -> tuple[np.ndarray, np.ndarray]:
        """21 (x, y) pixel points in ``rgb`` and their scores for one box (MediaPipe joint order)."""
        import cv2
        x0, y0, x1, y1 = box[:4]
        centre = np.array([(x0 + x1)/2, (y0 + y1)/2])
        side = max(x1 - x0, y1 - y0)*1.25                      # padding 1.25, square input
        src = np.float32([centre, centre + [0, -side/2], centre + [-side/2, -side/2]])
        half = self.POSE_SIZE/2
        dst = np.float32([[half, half], [half, 0], [0, 0]])
        warp = cv2.getAffineTransform(src, dst)
        crop = cv2.warpAffine(rgb, warp, (self.POSE_SIZE, self.POSE_SIZE), flags=cv2.INTER_LINEAR)
        x = (crop - np.array([123.675, 116.28, 103.53]))/np.array([58.395, 57.12, 57.375])  # RGB
        simcc_x, simcc_y = self.pose.run(None, {"input": x.transpose(2, 0, 1)[None].astype(np.float32)})
        sx, sy = simcc_x[0], simcc_y[0]
        locs = np.stack([sx.argmax(1), sy.argmax(1)], 1).astype(np.float64)/2.   # SimCC split ratio 2
        scores = (sx.max(1) + sy.max(1))/2
        points = centre + (locs/self.POSE_SIZE - .5)*side
        return points, scores


def _box_of(d: Detection, width: int, height: int):
    xy = d.image[:, :2]*[width, height]
    return (*xy.min(0), *xy.max(0))


def _overlap(a, b) -> float:
    """Intersection over the smaller box."""
    ix = max(0., min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0., min(a[3], b[3]) - max(a[1], b[1]))
    smaller = min((a[2]-a[0])*(a[3]-a[1]), (b[2]-b[0])*(b[3]-b[1]))
    return ix*iy/smaller if smaller > 0 else 0.


class HybridDetector:
    """MediaPipe (with its usual rescue) first; RTMDet boxes for missed hands (see module doc)."""
    def __init__(self, primary, model_path: Path, rtm_dir: Path, detection: float, presence: float,
                 num_hands: int = 2, pose_threshold: float = .45, fit_3d: bool = True, max_boxes: int = 4):
        from .model import Detector
        self.primary = primary
        self.crop_reader = Detector(model_path, detection, presence, presence, mode="image", num_hands=1)
        self.rtm = RtmHand(rtm_dir)
        self.num_hands = num_hands
        self.pose_threshold = pose_threshold
        self.fit_3d = fit_3d
        self.max_boxes = max_boxes
        self.stats = {"boxes": 0, "mediapipe_in_box": 0, "rtmpose_fitted": 0, "rtmpose_rejected": 0}

    def detect(self, rgb, timestamp_s, full_bgr=None):
        from .model import Detector
        detections = (self.primary.detect(rgb, timestamp_s) if isinstance(self.primary, Detector)
                      else self.primary.detect(rgb, timestamp_s, full_bgr))
        if len(detections) >= self.num_hands:
            return detections
        height, width = rgb.shape[:2]
        taken = [_box_of(d, width, height) for d in detections]
        for box in self.rtm.tiled_boxes(rgb)[:self.max_boxes]:
            if len(detections) >= self.num_hands:
                break
            if any(_overlap(box, t) > .4 for t in taken):
                continue
            self.stats["boxes"] += 1
            found = self._mediapipe_in_box(rgb, box, width, height)
            if found is None:
                found = self._rtmpose(rgb, box, width, height)
            if found is None:
                continue
            found.index = len(detections)
            detections.append(found)
            taken.append(_box_of(found, width, height))
        return detections

    def _mediapipe_in_box(self, rgb, box, width, height):
        from .model import square_box
        x0, y0, x1, y1 = box[:4]
        cx, cy, side = (x0 + x1)/2, (y0 + y1)/2, max(x1 - x0, y1 - y0)*1.6
        crop_box = square_box(cx, cy, side, width, height)
        a, b, c, d = crop_box
        hits = self.crop_reader.detect(np.ascontiguousarray(rgb[b:d, a:c]), 0.)
        if not hits:
            return None
        mapped = map_crop_detection(hits[0], crop_box, width, height, "hand_detector", "rtmdet_box")
        wrist = mapped.image[0, :2]*[width, height]
        pad = .25*max(x1 - x0, y1 - y0)
        if not (x0 - pad <= wrist[0] <= x1 + pad and y0 - pad <= wrist[1] <= y1 + pad):
            return None                       # MediaPipe read a different hand in the crop
        self.stats["mediapipe_in_box"] += 1
        return mapped

    def _rtmpose(self, rgb, box, width, height):
        points, scores = self.rtm.keypoints(rgb, box)
        if float(np.mean(scores)) < self.pose_threshold or not self.fit_3d:
            self.stats["rtmpose_rejected"] += 1
            return None
        from .handfit import fit_hand
        world = fit_hand(points, scores)
        if world is None:
            self.stats["rtmpose_rejected"] += 1
            return None
        image = np.zeros((21, 3))
        image[:, 0], image[:, 1] = points[:, 0]/width, points[:, 1]/height
        # image z: wrist-relative depth in roughly x units, from the fitted 3D (MediaPipe convention).
        size = np.ptp(points[:, 0]) + 1e-6
        world_size = np.ptp(world[:, 0]) + 1e-6
        image[:, 2] = (world[:, 2] - world[0, 2])*(size/world_size)/width
        self.stats["rtmpose_fitted"] += 1
        return Detection(image, world, "Right", .5, 0, "hand_detector", "rtmpose_fitted_3d")

    def close(self):
        self.primary.close()
        self.crop_reader.close()
