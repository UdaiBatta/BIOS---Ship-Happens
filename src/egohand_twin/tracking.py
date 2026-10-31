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
    image_filter: OneEuro = field(default_factory=OneEuro)
    world_filter: OneEuro = field(default_factory=OneEuro)


def right_probability(d: Detection):
    return d.handedness_score if d.side == "Right" else 1. - d.handedness_score


def record(track: Track, state: str, age: float, detection=None, image=None, world=None):
    return {
        "track_id": track.id,
        "state": state,
        "observed": detection is not None,
        "seconds_since_observed": round(age, 6),
        "side": "Right" if track.p_right >= .5 else "Left",
        "side_probability_right_smoothed": track.p_right,
        "detection_index": detection.index if detection else None,
        "detection_origin": detection.origin if detection else None,
        "raw_side": detection.side if detection else None,
        "handedness_score": detection.handedness_score if detection else None,
        "image_xyz_raw": detection.image.tolist() if detection else None,
        "world_xyz_m_raw": detection.world.tolist() if detection else None,
        "image_xyz": image.tolist() if image is not None else None,
        "world_xyz_m": world.tolist() if world is not None else None,
    }


class IdentityTracker:
    """Short-term associations, not biometric or guaranteed anatomical identities."""
    def __init__(self, predict_s=.15, retain_s=.8, smoothing=True, frame_size=None):
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
                t.p_right = .85 * t.p_right + .15 * right_probability(d)
                t.detection, t.last_seen = d, time
                records.append(self._observed(t, d, time, state))
                matched_tracks.add(t.id)
                matched_detections.add(int(col))
        for index, d in enumerate(detections):
            if index not in matched_detections:
                t = Track(self.next_id, d, time, right_probability(d))
                self.next_id += 1
                self.tracks[t.id] = t
                matched_tracks.add(t.id)
                records.append(self._observed(t, d, time, "observed"))
        for t in self.tracks.values():
            if t.id in matched_tracks:
                continue
            self._missing.add(t.id)
            age = time - t.last_seen
            if age <= self.predict_s:
                image = t.detection.image.copy()
                image[:, :2] += t.velocity * age
                # No 3D prediction: unseen articulation is unknown.
                records.append(record(t, "predicted", age, image=image))
            else:
                records.append(record(t, "lost", age))
        return sorted(records, key=lambda r: r["track_id"])

    def _observed(self, t, d, time, state):
        image = t.image_filter(d.image, time) if self.smoothing else d.image
        world = t.world_filter(d.world, time) if self.smoothing else d.world
        return record(t, state, 0., d, image, world)


def baseline_records(detections):
    """Per-result index IDs intentionally have no continuity guarantee."""
    return [record(Track(i + 1, d, 0., right_probability(d)), "observed", 0.,
                   d, d.image, d.world) for i, d in enumerate(detections)]
