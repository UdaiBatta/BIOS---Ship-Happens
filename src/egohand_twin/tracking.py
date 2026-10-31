from __future__ import annotations

from dataclasses import dataclass, field
import math

import numpy as np
from scipy.optimize import linear_sum_assignment

from .model import Detection


class OneEuro:
    """Adaptive low-pass filter, applied independently to each xyz coordinate."""
    def __init__(self, min_cutoff=1.7, beta=.03, derivative_cutoff=1.):
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.derivative_cutoff = derivative_cutoff
        self.value = self.raw = self.derivative = None
        self.time = None

    @staticmethod
    def alpha(cutoff, dt):
        return 1. / (1. + 1. / (2. * math.pi * cutoff * dt))

    def __call__(self, value, time):
        value = np.asarray(value, dtype=float)
        if self.time is None or time - self.time > .2:
            self.value, self.raw = value.copy(), value.copy()
            self.derivative = np.zeros_like(value)
        else:
            dt = max(time - self.time, 1e-6)
            derivative = (value - self.raw) / dt
            a = self.alpha(self.derivative_cutoff, dt)
            self.derivative = a * derivative + (1 - a) * self.derivative
            cutoff = self.min_cutoff + self.beta * np.abs(self.derivative)
            a = self.alpha(cutoff, dt)
            self.value = a * value + (1 - a) * self.value
            self.raw = value.copy()
        self.time = time
        return self.value.copy()


@dataclass
class Track:
    id: int
    detection: Detection
    last_seen: float
    p_right: float
    velocity: np.ndarray = field(default_factory=lambda: np.zeros(2))
    side: str | None = None          # Left / Right / unknown; changes only past the hysteresis band
    image_filter: OneEuro = field(default_factory=OneEuro)
    world_filter: OneEuro = field(default_factory=OneEuro)


def right_probability(d: Detection):
    return d.handedness_score if d.side == "Right" else 1. - d.handedness_score


EDGE_MARGIN = .02  # normalized image units


def missing_reason(track: Track, age: float) -> tuple[str, str]:
    """Explain why a track is not observed, using only evidence the tracker has.

    Returns (reason, basis). ``out_of_view`` is inferred when the wrist extrapolated
    from the last observation (velocity x min(age, 0.2 s)) lies outside the image, or
    when the last observed landmarks touched the image border. Everything else is
    ``unknown``: the tracker cannot tell occlusion, blur, a low detector score or
    another person's hand apart, so it does not guess. This is an inference, not an
    observation; it can be wrong when a hand at the border is simply missed.
    """
    xy = track.detection.image[:, :2]
    extrapolated = xy[0] + track.velocity * min(age, .2)
    if np.any(extrapolated < 0) or np.any(extrapolated > 1):
        return "out_of_view", (f"extrapolated wrist ({extrapolated[0]:.3f}, {extrapolated[1]:.3f}) "
                               "outside the image")
    if np.any((xy < EDGE_MARGIN) | (xy > 1 - EDGE_MARGIN)):
        return "out_of_view", "last observed landmarks touched the image border"
    return "unknown", "no evidence separating occlusion, blur, low detector score or exit"


def record(track: Track, state: str, age: float, detection=None, image=None, world=None):
    out = {
        "track_id": track.id,
        "state": state,
        "observed": detection is not None,
        "seconds_since_observed": round(age, 6),
        "side": track.side or ("Right" if track.p_right >= .5 else "Left"),
        "side_probability_right_smoothed": track.p_right,
        "detection_index": detection.index if detection else None,
        "detection_origin": detection.origin if detection else None,
        "detection_origin_detail": detection.origin_detail if detection else None,
        # Offline anatomical identity is not known while processing; `egohand identity
        # --write-jsonl` writes a separate file with track-level votes.
        "anatomical_side": "unknown",
        # No calibrated hand-level confidence exists; never copied from handedness_score.
        "confidence": None,
        "raw_side": detection.side if detection else None,
        "handedness_score": detection.handedness_score if detection else None,
        "image_xyz_raw": detection.image.tolist() if detection else None,
        "world_xyz_m_raw": detection.world.tolist() if detection else None,
        "image_xyz": image.tolist() if image is not None else None,
        "world_xyz_m": world.tolist() if world is not None else None,
    }
    # Schema provenance vocabulary: "predicted" = output of a learned model (MediaPipe),
    # "inferred" = produced by a rule (filtering, extrapolation, voting), "measured" = direct
    # measurement. Not to be confused with the tracker state "predicted".
    # Which model produced this observation's 2D points, and where its hand-relative 3D comes from.
    # RTMPose-only hands (hybrid preset) have NO observed 3D: their world_xyz_m_raw is fitted from
    # the 2D points plus a typical hand's depth (handfit), so it is "inferred", never "predicted".
    fitted = detection is not None and detection.origin_detail == "rtmpose_fitted_3d"
    out["landmark_source"] = (("rtmpose" if fitted else "mediapipe") if detection is not None else None)
    out["world_source"] = (("fitted_from_2d" if fitted else "mediapipe_world") if detection is not None else None)
    out["side_source"] = (("inherited_from_track" if detection is not None and abs(detection.handedness_score - .5) < 1e-9
                           else "tracker_running_vote") if detection is not None else "tracker_running_vote")
    if detection is not None:
        out["provenance"] = {"image_xyz_raw": "predicted", "world_xyz_m_raw": "inferred" if fitted else "predicted",
                             "image_xyz": "inferred", "world_xyz_m": "inferred",
                             "side": "inferred", "handedness_score": "predicted"}
    elif image is not None:
        out["provenance"] = {"image_xyz": "inferred", "missing_reason": "inferred", "side": "inferred"}
    else:
        out["provenance"] = {"missing_reason": "inferred", "side": "inferred"}
    if detection is None:
        reason, basis = missing_reason(track, age)
        out["missing_reason"], out["missing_reason_basis"] = reason, basis
        out["missing_reason_provenance"] = "inferred"
    else:
        out["missing_reason"] = out["missing_reason_basis"] = out["missing_reason_provenance"] = None
    return out


def _box_overlap(a: np.ndarray, b: np.ndarray) -> float:
    """Intersection of two landmark boxes over the smaller box (normalized image coordinates)."""
    (ax0, ay0), (ax1, ay1) = a.min(0), a.max(0)
    (bx0, by0), (bx1, by1) = b.min(0), b.max(0)
    ix, iy = max(0., min(ax1, bx1) - max(ax0, bx0)), max(0., min(ay1, by1) - max(ay0, by0))
    smaller = min((ax1 - ax0)*(ay1 - ay0), (bx1 - bx0)*(by1 - by0))
    return float(ix*iy/smaller) if smaller > 0 else 0.


class IdentityTracker:
    """Short-term associations, not biometric or guaranteed anatomical identities."""
    def __init__(self, predict_s=.15, retain_s=.8, smoothing=True, frame_size=None, box_link=False,
                 side_weights: dict | None = None, side_hysteresis: float = 0.):
        """``side_weights``: how much one detection's left/right score moves its track's running
        P(right), per detection path (``origin_detail`` or ``origin``; key ``default``). The
        original behaviour is 0.15 for every path. A weight of 0 means the detection carries no
        side evidence and the track keeps (inherits) its side; detections with a neutral score
        (0.5, e.g. RTMPose-only hands) never change the side. ``side_hysteresis``: the shown side
        changes only when P(right) passes 0.5 +/- this margin (0 = flip at 0.5, as before)."""
        """``frame_size=(width, height)`` measures association distances in image-diagonal
        units (isotropic in pixels). ``None`` keeps the original normalized x/y units,
        in which a vertical pixel counts ~1.8x a horizontal pixel on 16:9 video."""
        if predict_s < 0 or retain_s < predict_s:
            raise ValueError("Require 0 <= predict_s <= retain_s")
        self.units = (np.array(frame_size, dtype=float)/np.hypot(*frame_size)
                      if frame_size is not None else np.ones(2))
        self.predict_s, self.retain_s = predict_s, retain_s
        self.smoothing = smoothing
        self.tracks: dict[int, Track] = {}
        self.next_id = 1
        self.last_time = None
        self.reacquisitions = 0
        self.box_link = box_link
        self.side_weights = {"default": .15, **(side_weights or {})}
        self.side_hysteresis = side_hysteresis
        self.box_links = 0
        self.ghosts_suppressed = 0
        self._missing: set[int] = set()

    def _cost(self, t: Track, d: Detection, time):
        age = time - t.last_seen
        predicted = t.detection.image[0, :2] + t.velocity * min(age, .2)
        distance = np.linalg.norm((d.image[0, :2] - predicted) * self.units)
        # Finite spatial gate prevents distant re-entries inheriting a stale ID.
        if distance > min(.32, .10 + age * .55):
            return 1e6
        a = t.detection.image[:, :2] - t.detection.image[0, :2]
        b = d.image[:, :2] - d.image[0, :2]
        a /= max(np.linalg.norm(a[9]), .01)
        b /= max(np.linalg.norm(b[9]), .01)
        shape = min(float(np.sqrt(np.mean((a - b) ** 2))), 2.)
        side = abs(t.p_right - right_probability(d))
        return float(distance + .035 * shape + .11 * side)

    def update(self, detections: list[Detection], time: float) -> list[dict]:
        if self.last_time is not None and time <= self.last_time:
            raise ValueError("Tracker timestamps must strictly increase")
        self.last_time = time
        records = []
        for key, t in list(self.tracks.items()):
            if time - t.last_seen > self.retain_s:
                records.append(record(t, "retired", time - t.last_seen))
                del self.tracks[key]
                self._missing.discard(key)
        active = list(self.tracks.values())
        matched_tracks, matched_detections = set(), set()
        if active and detections:
            costs = np.array([[self._cost(t, d, time) for d in detections] for t in active])
            rows, cols = linear_sum_assignment(costs)
            for row, col in zip(rows, cols):
                if costs[row, col] >= 1e6:
                    continue
                t, d = active[row], detections[col]
                dt = time - t.last_seen
                velocity = (d.image[0, :2] - t.detection.image[0, :2]) / dt
                speed = np.linalg.norm(velocity * self.units)
                if speed > 2.:
                    velocity *= 2. / speed
                t.velocity = .5 * velocity + .5 * t.velocity
                state = "reacquired" if t.id in self._missing else "observed"
                if state == "reacquired":
                    self.reacquisitions += 1
                self._missing.discard(t.id)
                self._update_side(t, d)
                t.detection, t.last_seen = d, time
                records.append(self._observed(t, d, time, state))
                matched_tracks.add(t.id)
                matched_detections.add(int(col))
        # Second pass: a detection whose hand box mostly covers a just-missed track's predicted box is
        # the same hand (e.g. a rescue crop placed the wrist differently, failing the wrist gate).
        # Linking them keeps one identity and avoids drawing a "predicted" ghost over an observed hand.
        if self.box_link:
            for index, d in enumerate(detections):
                if index in matched_detections:
                    continue
                best, best_overlap = None, .5
                for t in active:
                    age = time - t.last_seen
                    if t.id in matched_tracks or age > self.predict_s:
                        continue
                    shifted = t.detection.image[:, :2] + t.velocity*age
                    overlap = _box_overlap(shifted, d.image[:, :2])
                    if overlap > best_overlap:
                        best, best_overlap = t, overlap
                if best is not None:
                    self.box_links += 1
                    self._missing.discard(best.id)
                    self._update_side(best, d)
                    best.detection, best.last_seen = d, time
                    records.append(self._observed(best, d, time, "observed"))
                    matched_tracks.add(best.id)
                    matched_detections.add(index)
        for index, d in enumerate(detections):
            if index not in matched_detections:
                t = self._new_track(d, time)
                self.tracks[t.id] = t
                matched_tracks.add(t.id)
                records.append(self._observed(t, d, time, "observed"))
        observed_boxes = [d.image[:, :2] for d in detections]
        for t in self.tracks.values():
            if t.id in matched_tracks:
                continue
            self._missing.add(t.id)
            age = time - t.last_seen
            shifted = t.detection.image[:, :2] + t.velocity*age
            if self.box_link and age <= self.predict_s and any(
                    _box_overlap(shifted, box) > .5 for box in observed_boxes):
                # Its predicted position sits on a hand observed this frame: drawing it would put a
                # second ("ghost") skeleton on that hand. Report it as lost instead of predicted.
                self.ghosts_suppressed += 1
                records.append(record(t, "lost", age))
                continue
            if age <= self.predict_s:
                image = t.detection.image.copy()
                image[:, :2] += t.velocity * age
                # No 3D prediction: unseen articulation is unknown.
                records.append(record(t, "predicted", age, image=image))
            else:
                records.append(record(t, "lost", age))
        return sorted(records, key=lambda r: r["track_id"])

    def _side_weight(self, d: Detection) -> float:
        if abs(d.handedness_score - .5) < 1e-9:
            return 0.                                   # no side evidence (e.g. RTMPose-only hand)
        w = self.side_weights
        return float(w.get(d.origin_detail or "", w.get(d.origin, w["default"])))

    def _update_side(self, t: Track, d: Detection):
        weight = self._side_weight(d)
        t.p_right = (1 - weight)*t.p_right + weight*right_probability(d)
        if t.side is None:
            t.side = "Right" if t.p_right >= .5 else "Left"
        elif t.side == "unknown":
            # undecided until the evidence leaves the hysteresis band (never forced)
            if t.p_right > .5 + self.side_hysteresis:
                t.side = "Right"
            elif t.p_right < .5 - self.side_hysteresis:
                t.side = "Left"
        elif t.side == "Left" and t.p_right > .5 + self.side_hysteresis:
            t.side = "Right"
        elif t.side == "Right" and t.p_right < .5 - self.side_hysteresis:
            t.side = "Left"

    def _new_track(self, d: Detection, time: float) -> Track:
        # A track's starting P(right) is the first detection's evidence, scaled by how much that
        # detection path is trusted (a zero-weight path starts the track at 0.5, side undecided).
        scale = min(1., self._side_weight(d)/self.side_weights["default"]) if self.side_weights["default"] else 1.
        t = Track(self.next_id, d, time, .5 + (right_probability(d) - .5)*scale)
        # No side evidence yet (zero-weight path or a neutral score): shown as "unknown", not guessed.
        t.side = "unknown" if scale == 0 or t.p_right == .5 else ("Right" if t.p_right > .5 else "Left")
        self.next_id += 1
        return t

    def _observed(self, t, d, time, state):
        image = t.image_filter(d.image, time) if self.smoothing else d.image
        world = t.world_filter(d.world, time) if self.smoothing else d.world
        return record(t, state, 0., d, image, world)


def baseline_records(detections):
    """Per-result index IDs intentionally have no continuity guarantee."""
    return [record(Track(i + 1, d, 0., right_probability(d)), "observed", 0.,
                   d, d.image, d.world) for i, d in enumerate(detections)]
