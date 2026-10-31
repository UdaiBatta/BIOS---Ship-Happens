"""Fast, cached access to run outputs written by egohand_twin.

Latency design:
- ``frames_index.npz`` (built once when a run completes) stores the byte offset,
  frame index and timestamp of every JSONL line. A time-range request does a binary
  search and ONE contiguous file read instead of scanning the whole JSONL.
- Small JSON artefacts (manifest, metrics, quality, queue, tracks) are cached in memory
  keyed by (path, mtime, size), so repeated UI polling costs no disk parsing.
- ``tracks.json`` precomputes per-track state lanes as run-length segments, so the
  timeline needs one small response instead of every frame.
- "lite" frame payloads keep only what a viewer draws (filtered 2D/3D, states, side
  probability, origin, missing reason) and round to 4 decimals; "full" returns records
  unchanged (raw values included) for analysis.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
import subprocess
import threading

from django.conf import settings
from django.core.cache import cache
import numpy as np

INDEX_NAME = "frames_index.npz"
TRACKS_NAME = "tracks.json"
LITE_HAND_KEYS = ("track_id", "state", "observed", "side", "side_probability_right_smoothed",
                  "anatomical_side", "detection_origin", "missing_reason", "seconds_since_observed")


class NotReady(Exception):
    """The run has not produced the requested artefact (yet)."""


# --------------------------------------------------------------------------- files
def allowed_media_path(path: str | Path) -> Path:
    """Resolve ``path`` and refuse anything outside EGOHAND_MEDIA_ROOTS (no traversal)."""
    resolved = Path(path).expanduser().resolve()
    for root in settings.MEDIA_ROOTS:
        if resolved == root or root in resolved.parents:
            if not resolved.is_file():
                raise FileNotFoundError(f"Not a file: {resolved.name}")
            return resolved
    raise PermissionError("Path is outside the allowed media folders (EGOHAND_MEDIA_ROOTS)")


def _stamp(path: Path) -> tuple:
    stat = path.stat()
    return (str(path), stat.st_mtime_ns, stat.st_size)


def cached_json(path: Path):
    if not path.exists():
        raise NotReady(path.name)
    key = "json:" + "|".join(map(str, _stamp(path)))
    value = cache.get(key)
    if value is None:
        value = json.loads(path.read_text())
        cache.set(key, value, timeout=None)
    return value


# --------------------------------------------------------------------------- index
def build_frame_index(run_dir: Path) -> Path:
    """Byte offsets, frame indices and timestamps for every landmarks.jsonl line."""
    offsets, frames, times = [], [], []
    position = 0
    with (run_dir/"landmarks.jsonl").open("rb") as f:
        for line in f:
            record = json.loads(line)
            offsets.append(position)
            frames.append(record["frame_index"])
            times.append(record["timestamp_s"])
            position += len(line)
    if times and np.any(np.diff(times) <= 0):
        raise ValueError("landmarks.jsonl timestamps are not strictly increasing")
    out = run_dir/INDEX_NAME
    np.savez(out, offsets=np.array(offsets + [position], np.int64), frame_index=np.array(frames, np.int64),
             timestamp_s=np.array(times, np.float64))
    return out


_index_lock = threading.Lock()


def load_index(run_dir: Path) -> dict:
    path = run_dir/INDEX_NAME
    if not path.exists():
        if not (run_dir/"COMPLETE").exists():
            raise NotReady("run not complete")
        with _index_lock:
            if not path.exists():
                build_frame_index(run_dir)
    key = "index:" + "|".join(map(str, _stamp(path)))
    value = cache.get(key)
    if value is None:
        with np.load(path) as data:
            value = {k: data[k] for k in data.files}
        cache.set(key, value, timeout=None)
    return value


def _round(value, digits=4):
    if isinstance(value, float):
        return round(value, digits)
    if isinstance(value, list):
        return [_round(v, digits) for v in value]
    return value


def lite_frame(record: dict) -> dict:
    hands = []
    for hand in record["hands"]:
        item = {k: hand.get(k) for k in LITE_HAND_KEYS}
        item["image_xyz"] = _round(hand.get("image_xyz"))
        item["world_xyz_m"] = _round(hand.get("world_xyz_m"))
        hands.append(item)
    return {"frame_index": record["frame_index"], "timestamp_s": record["timestamp_s"],
            "quality": record.get("quality"), "hands": hands}


def read_frames(run_dir: Path, start_s: float | None = None, end_s: float | None = None,
                max_frames: int = 600, detail: str = "lite") -> dict:
    """Frames with start_s <= t < end_s (run time base), at most ``max_frames``."""
    index = load_index(run_dir)
    times = index["timestamp_s"]
    lo = 0 if start_s is None else int(np.searchsorted(times, start_s, side="left"))
    hi = len(times) if end_s is None else int(np.searchsorted(times, end_s, side="left"))
    truncated = hi - lo > max_frames
    hi = min(hi, lo + max_frames)
    records = []
    if hi > lo:
        offsets = index["offsets"]
        with (run_dir/"landmarks.jsonl").open("rb") as f:
            f.seek(int(offsets[lo]))
            chunk = f.read(int(offsets[hi] - offsets[lo]))
        for line in chunk.splitlines():
            record = json.loads(line)
            records.append(lite_frame(record) if detail == "lite" else record)
    return {"frames": records, "count": len(records), "truncated": truncated,
            "next_start_s": float(times[hi]) if truncated else None, "detail": detail}


def read_frame(run_dir: Path, frame_index: int, detail: str = "full") -> dict:
    index = load_index(run_dir)
    position = int(np.searchsorted(index["frame_index"], frame_index))
    if position >= len(index["frame_index"]) or index["frame_index"][position] != frame_index:
        raise KeyError(frame_index)
    with (run_dir/"landmarks.jsonl").open("rb") as f:
        f.seek(int(index["offsets"][position]))
        record = json.loads(f.readline())
    return lite_frame(record) if detail == "lite" else record


# --------------------------------------------------------------------------- tracks
def build_tracks(run_dir: Path) -> Path:
    """Per-track run-length state lanes: [{state, side, start_s, end_s, frames}]."""
    tracks: dict[int, dict] = {}
    with (run_dir/"landmarks.jsonl").open() as f:
        for line in f:
            record = json.loads(line)
            t = record["timestamp_s"]
            for hand in record["hands"]:
                track = tracks.setdefault(hand["track_id"], {"track_id": hand["track_id"], "segments": [],
                                                             "observed_frames": 0})
                state = "observed" if hand["observed"] else hand["state"]
                track["observed_frames"] += bool(hand["observed"])
                segments = track["segments"]
                last = segments[-1] if segments else None
                if last and last["state"] == state and last["side"] == hand["side"] and \
                        last.get("missing_reason") == hand.get("missing_reason"):
                    last["end_s"], last["frames"] = t, last["frames"] + 1
                else:
                    segments.append({"state": state, "side": hand["side"], "start_s": t, "end_s": t, "frames": 1,
                                     "missing_reason": hand.get("missing_reason")})
    payload = {"tracks": [tracks[k] for k in sorted(tracks)],
               "note": "end_s is the timestamp of the last frame in the segment (inclusive)."}
    out = run_dir/TRACKS_NAME
    out.write_text(json.dumps(payload, separators=(",", ":")))
    return out


def tracks(run_dir: Path) -> dict:
    path = run_dir/TRACKS_NAME
    if not path.exists():
        if not (run_dir/"COMPLETE").exists():
            raise NotReady("run not complete")
        build_tracks(run_dir)
    return cached_json(path)


def events(run_dir: Path, start_s: float | None = None, end_s: float | None = None) -> list[dict]:
    path = run_dir/"tracking_events.csv"
    if not path.exists():
        raise NotReady(path.name)
    rows = []
    with path.open() as f:
        for row in csv.DictReader(f):
            t = float(row["timestamp_s"])
            if (start_s is None or t >= start_s) and (end_s is None or t < end_s):
                rows.append({**row, "frame_index": int(row["frame_index"]), "timestamp_s": t,
                             "track_id": int(row["track_id"])})
    return rows


# --------------------------------------------------------------------------- frames as images
def frame_jpeg(video_path: Path, video_sha: str, frame_index: int, pts_s: float, width: int) -> Path:
    """Exact frame as JPEG via FFmpeg accurate seek to the frame's PTS; cached on disk."""
    out = settings.DATA_DIR/"frames"/video_sha[:16]/f"{frame_index:06d}_{width}.jpg"
    if out.exists():
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp.jpg")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{pts_s:.6f}", "-i", str(video_path),
                    "-frames:v", "1", "-vf", f"scale={width}:-2", "-q:v", "3", str(tmp)],
                   check=True, capture_output=True, timeout=60)
    tmp.replace(out)
    return out


def video_timestamps(video) -> np.ndarray:
    """Per-frame presentation timestamps (relative to the first), probed once per video and cached."""
    from egohand_twin.pipeline import probe
    path = settings.DATA_DIR/"timestamps"/f"{video.sha256}.npy"
    key = f"ts:{video.sha256}"
    value = cache.get(key)
    if value is not None:
        return value
    if path.exists():
        value = np.load(path)
    else:
        absolute = np.asarray(probe(Path(video.path))["timestamps"], np.float64)
        value = absolute - absolute[0]
        path.parent.mkdir(parents=True, exist_ok=True)
        np.save(path, value)
    cache.set(key, value, timeout=None)
    return value
