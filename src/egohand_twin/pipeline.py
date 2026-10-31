from __future__ import annotations

import csv
from datetime import datetime, timezone
import importlib.metadata
import json
from pathlib import Path
import platform
import shutil
import subprocess
import time

import cv2
import numpy as np
import psutil

from .model import COORDINATES, MODEL_URL, CropRescueDetector, Detector, sha256
from .render import RerunSink, VideoSink, composite
from .tracking import IdentityTracker, baseline_records


def probe(path: Path):
    if not shutil.which("ffprobe"):
        raise RuntimeError("FFprobe is required for source presentation timestamps")
    result = subprocess.run([
        "ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
        "stream=width,height,avg_frame_rate,r_frame_rate,duration,nb_frames:frame=best_effort_timestamp_time",
        "-of", "json", str(path)], check=True, capture_output=True, text=True)
    data = json.loads(result.stdout)
    stream = data["streams"][0]
    timestamps = [float(f["best_effort_timestamp_time"]) for f in data.get("frames", [])
                  if "best_effort_timestamp_time" in f]
    if not timestamps or np.any(np.diff(timestamps) <= 0):
        raise ValueError("Missing/non-increasing presentation timestamps; transcode input to CFR first")
    numerator, denominator = stream["avg_frame_rate"].split("/")
    fps = float(numerator)/float(denominator)
    if not np.isfinite(fps) or fps <= 0:
        raise ValueError("Video has invalid frame rate")
    delta = np.diff(timestamps)
    cfr = len(delta) == 0 or bool(np.max(np.abs(delta - 1/fps)) < .001)
    return {**stream, "fps": fps, "cfr": cfr, "timestamps": timestamps}


def process(args):
    started = time.perf_counter()
    source, out = Path(args.video), Path(args.out)
    if not source.is_file():
        raise FileNotFoundError(source)
    if not Path(args.model).is_file():
        raise FileNotFoundError("Model missing. Run: egohand fetch-model")
    if out.exists() and any(out.iterdir()):
        raise ValueError("Output directory is nonempty; choose a new --out directory")
    info = probe(source)
    if not info["cfr"] and not args.no_video:
        raise ValueError("VFR input: use --no-video --rrd for exact-timestamp replay, or transcode to CFR")
    out.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(str(source))
    if not cap.isOpened():
        raise ValueError("OpenCV could not decode video")
    detector = video_sink = rerun_sink = None
    tracker = IdentityTracker(args.predict_seconds, args.retain_seconds, not args.no_smoothing)
    rss = psutil.Process()
    peak_rss = rss.memory_info().rss
    latency, sample_rows, events = [], [], []
    previous_states = {}
    counts = {"observed": 0, "reacquired": 0, "predicted": 0, "lost": 0, "retired": 0}
    observed_frames = processed = 0
    first_s = last_s = None
    best_poster_hands = -1
    try:
        detector_class = CropRescueDetector if args.rescue_crop else Detector
        detector = detector_class(Path(args.model), detection=args.detection_threshold,
                                  presence=args.presence_threshold, tracking=args.tracking_threshold,
                                  mode=args.detector_mode, num_hands=args.num_hands)
        if not args.no_video:
            video_sink = VideoSink(out/"preview.mp4", info["fps"]/args.stride)
        if args.rrd:
            rerun_sink = RerunSink(out/"replay.rrd")
        fields = ["frame_index", "timestamp_s", "track_id", "state", "observed", "side",
                  "handedness_score", "landmark_index", "x_norm", "y_norm", "z_norm",
                  "world_x_m", "world_y_m", "world_z_m", "raw_x_norm", "raw_y_norm",
                  "raw_z_norm", "raw_world_x_m", "raw_world_y_m", "raw_world_z_m"]
        with (out/"landmarks.jsonl").open("w") as jf, (out/"landmarks.csv").open("w", newline="") as cf:
            writer = csv.DictWriter(cf, fieldnames=fields)
            writer.writeheader()
            frame_index = -1
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                frame_index += 1
                if frame_index >= len(info["timestamps"]):
                    raise RuntimeError("Decoded frame count exceeds timestamp count")
                pts = info["timestamps"][frame_index]
                timestamp = pts - info["timestamps"][0]
                if timestamp < args.start_seconds:
                    continue
                if args.duration is not None and timestamp >= args.start_seconds + args.duration:
                    break
                if frame_index % args.stride:
                    continue
                if args.max_frames is not None and processed >= args.max_frames:
                    break
                h, w = frame.shape[:2]
                scale = min(1., args.max_width/w)
                resized = cv2.resize(frame, (round(w*scale), round(h*scale))) if scale < 1 else frame
                inference_start = time.perf_counter()
                detections = detector.detect(cv2.cvtColor(resized, cv2.COLOR_BGR2RGB), timestamp)
                latency.append(time.perf_counter() - inference_start)
                hands = (tracker.update(detections, timestamp) if args.identity == "persistent"
                         else baseline_records(detections))
                sample = {"frame_index": frame_index, "timestamp_s": timestamp,
                          "source_pts_s": pts, "hands": hands}
                jf.write(json.dumps(sample, separators=(",", ":"), allow_nan=False)+"\n")
                observed_frames += int(bool(detections))
                for hand in hands:
                    counts[hand["state"]] += 1
                    previous = previous_states.get(hand["track_id"])
                    if previous != hand["state"]:
                        events.append({"frame_index": frame_index, "timestamp_s": timestamp,
                                       "track_id": hand["track_id"], "side": hand["side"],
                                       "from_state": previous, "to_state": hand["state"]})
                    previous_states[hand["track_id"]] = hand["state"]
                    base = {k: sample[k] for k in ["frame_index", "timestamp_s"]}
                    base.update({k: hand[k] for k in ["track_id", "state", "observed", "side", "handedness_score"]})
                    for j in (range(21) if hand["image_xyz"] is not None else [-1]):
                        row = {**base, "landmark_index": j}
                        for key, columns in [
                            ("image_xyz", ["x_norm", "y_norm", "z_norm"]),
                            ("world_xyz_m", ["world_x_m", "world_y_m", "world_z_m"]),
                            ("image_xyz_raw", ["raw_x_norm", "raw_y_norm", "raw_z_norm"]),
                            ("world_xyz_m_raw", ["raw_world_x_m", "raw_world_y_m", "raw_world_z_m"])]:
                            if j >= 0 and hand[key] is not None:
                                row.update(zip(columns, hand[key][j]))
                        writer.writerow(row)
                    sample_rows.append((frame_index, timestamp, hand))
                if video_sink:
                    rendered = composite(frame, sample)
                    video_sink.write(rendered)
                    if len(detections) > best_poster_hands:
                        cv2.imwrite(str(out/"preview.jpg"), rendered)
                        best_poster_hands = len(detections)
                if rerun_sink:
                    rerun_sink.write(resized, sample)
                processed += 1
                first_s = timestamp if first_s is None else first_s
                last_s = timestamp
                peak_rss = max(peak_rss, rss.memory_info().rss)
                if processed % 100 == 0:
                    print(f"Processed {processed} frames; source time {timestamp:.2f}s", flush=True)
        if processed == 0:
            raise ValueError("No frames processed; check input and selected time range")
        if video_sink:
            video_sink.close()
            video_sink = None
        if rerun_sink:
            rerun_sink.close()
            rerun_sink = None
        shape = (len(sample_rows), 21, 3)
        arrays = {key: np.full(shape, np.nan, np.float32) for key in [
            "image_xyz", "world_xyz_m", "image_xyz_raw", "world_xyz_m_raw"]}
        for index, (_, _, hand) in enumerate(sample_rows):
            for key, values in arrays.items():
                if hand[key] is not None:
                    values[index] = hand[key]
        np.savez_compressed(out/"landmarks.npz", **arrays,
                            frame_index=np.array([r[0] for r in sample_rows], dtype=np.int64),
                            timestamp_s=np.array([r[1] for r in sample_rows]),
                            track_id=np.array([r[2]["track_id"] for r in sample_rows], dtype=np.int64),
                            state=np.array([r[2]["state"] for r in sample_rows], dtype="U12"),
                            observed=np.array([r[2]["observed"] for r in sample_rows], dtype=bool))
        peak_rss = max(peak_rss, rss.memory_info().rss)
        with (out/"tracking_events.csv").open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["frame_index", "timestamp_s", "track_id", "side", "from_state", "to_state"])
            writer.writeheader()
            writer.writerows(events)
        elapsed = time.perf_counter() - started
        metrics = {
            "processed_frames": processed, "frames_with_observed_hands": observed_frames,
            "observed_frame_fraction": observed_frames/processed,
            "track_state_samples": counts,
            "track_ids_created": tracker.next_id-1 if args.identity == "persistent" else None,
            "reacquisitions": tracker.reacquisitions if args.identity == "persistent" else None,
            "first_timestamp_s": first_s, "last_timestamp_s": last_s,
            "processing_seconds": elapsed, "end_to_end_fps": processed/elapsed,
            "inference_seconds": sum(latency), "inference_fps": processed/sum(latency),
            "inference_p50_ms": float(np.percentile(latency, 50)*1000),
            "inference_p95_ms": float(np.percentile(latency, 95)*1000),
            "sampled_peak_process_rss_mb": peak_rss/1024**2,
            "accuracy": None, "identity_switches": None,
            "notes": ["Coverage is not recall or accuracy; labels are required.",
                      "Reacquisitions are tracker decisions, not verified identity recovery.",
                      "RSS is sampled at frame/export boundaries and may miss short peaks.",
                      "End-to-end timing starts at process entry, includes probe, model setup, rendering, logging and exports; excludes interpreter/import startup and downloads.",
                      "NPZ has one row per track-state sample; missing values are NaN; JSONL retains empty frames."],
        }
        (out/"metrics.json").write_text(json.dumps(metrics, indent=2)+"\n")
        manifest = {
            "schema_version": "0.1", "created_utc": datetime.now(timezone.utc).isoformat(),
            "source": {"name": source.name, "sha256": sha256(source),
                       "width": int(info["width"]), "height": int(info["height"]),
                       "fps": info["fps"], "cfr": info["cfr"], "total_frames": len(info["timestamps"])},
            "model_sha256": sha256(Path(args.model)), "official_model_reference": MODEL_URL,
            "coordinates": COORDINATES,
            "parameters": {k: v for k, v in vars(args).items() if k not in ["func", "video", "out", "model"]},
            "environment": {"platform": platform.platform(), "machine": platform.machine(),
                            "python": platform.python_version(), "packages": {
                                name: importlib.metadata.version(name) for name in [
                                    "mediapipe", "numpy", "scipy", "opencv-contrib-python", "psutil"]}},
            "preview": {"audio": False, "time_origin_s": first_s,
                        "note": "Muted CFR inspection render; source timestamps are printed on each frame."},
            "privacy": "Source footage and all derived artifacts must stay outside the public repository.",
        }
        (out/"manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")
        (out/"COMPLETE").write_text("Processing completed successfully.\n")
        print(json.dumps(metrics, indent=2))
        return metrics
    finally:
        cap.release()
        if detector:
            detector.close()
        if video_sink:
            video_sink.close()
        if rerun_sink:
            rerun_sink.close()
