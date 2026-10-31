from __future__ import annotations

import csv
from datetime import date, datetime, timezone
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

from .governance import load as load_governance
from .quality import frame_stats
from .model import COORDINATES, MODEL_URL, CropRescueDetector, Detector, MultiViewDetector, sha256
from .render import RerunSink, VideoSink, composite
from .tracking import IdentityTracker, baseline_records


def _ffprobe_json(path: Path, *extra: str) -> dict:
    result = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", *extra,
                             "-of", "json", str(path)], check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def _frame_timestamps(path: Path, read_intervals: str | None = None) -> list[float]:
    extra = ["-read_intervals", read_intervals] if read_intervals else []
    data = _ffprobe_json(path, *extra, "-show_entries", "frame=best_effort_timestamp_time")
    return [float(f["best_effort_timestamp_time"]) for f in data.get("frames", [])
            if "best_effort_timestamp_time" in f]


def _packet_timestamps(path: Path) -> list[float] | None:
    """Presentation timestamps from demuxed packets, sorted into presentation order.

    Returns None when packets cannot be trusted as one frame each (missing PTS,
    discard flags or duplicate PTS); callers then decode frames instead.
    """
    data = _ffprobe_json(path, "-show_entries", "packet=pts_time,flags")
    packets = data.get("packets", [])
    if not packets or any("pts_time" not in p or "D" in p.get("flags", "") for p in packets):
        return None
    timestamps = sorted(float(p["pts_time"]) for p in packets)
    if np.any(np.diff(timestamps) <= 0):
        return None
    return timestamps


def probe(path: Path, timestamp_source: str = "auto", check_frames: int = 48):
    """Stream metadata and per-frame presentation timestamps.

    ``frames`` decodes the whole stream with FFprobe (exact but slow: it decodes
    every frame even when only an interval is processed). ``auto`` uses demuxed
    packet PTS, verified against decoded frame timestamps for the first
    ``check_frames`` frames and against the stream frame count, and falls back
    to ``frames`` on any disagreement. The pipeline additionally fails if more
    frames decode than timestamps exist.
    """
    if not shutil.which("ffprobe"):
        raise RuntimeError("FFprobe is required for source presentation timestamps")
    stream = _ffprobe_json(path, "-show_entries",
                           "stream=width,height,avg_frame_rate,r_frame_rate,duration,nb_frames")["streams"][0]
    timestamps, source, note = None, "frames", None
    if timestamp_source == "auto":
        packets = _packet_timestamps(path)
        decoded = _frame_timestamps(path, f"%+#{check_frames}")
        expected = int(stream["nb_frames"]) if str(stream.get("nb_frames", "")).isdigit() else None
        if packets is None:
            note = "packet timestamps unusable; decoded all frames"
        elif expected is not None and len(packets) != expected:
            note = f"packet count {len(packets)} != nb_frames {expected}; decoded all frames"
        elif not decoded or len(decoded) > len(packets) or \
                np.max(np.abs(np.asarray(decoded)-packets[:len(decoded)])) > 1e-6:
            note = "packet PTS disagree with decoded frame timestamps; decoded all frames"
        else:
            timestamps, source = packets, "packets_verified"
            note = f"packet PTS matched {len(decoded)} decoded frame timestamps"
    elif timestamp_source != "frames":
        raise ValueError("timestamp_source must be auto or frames")
    if timestamps is None:
        timestamps = _frame_timestamps(path)
    if not timestamps or np.any(np.diff(timestamps) <= 0):
        raise ValueError("Missing/non-increasing presentation timestamps; transcode input to CFR first")
    numerator, denominator = stream["avg_frame_rate"].split("/")
    fps = float(numerator)/float(denominator)
    if not np.isfinite(fps) or fps <= 0:
        raise ValueError("Video has invalid frame rate")
    delta = np.diff(timestamps)
    cfr = len(delta) == 0 or bool(np.max(np.abs(delta - 1/fps)) < .001)
    return {**stream, "fps": fps, "cfr": cfr, "timestamps": timestamps,
            "timestamp_source": source, "timestamp_note": note}


def build_detector(args):
    """Construct the detector exactly as configured by process options (shared with parallel.py)."""
    options = dict(detection=args.detection_threshold, presence=args.presence_threshold,
                   tracking=args.tracking_threshold, mode=args.detector_mode, num_hands=args.num_hands)
    rescue = [s for s in (getattr(args, "rescue", None) or "").split(",") if s]
    if args.rescue_crop and rescue:
        raise ValueError("Use either --rescue-crop (historical) or --rescue, not both")
    if args.rescue_crop:
        detector = CropRescueDetector(Path(args.model), **options)
    elif rescue:
        detector = MultiViewDetector(Path(args.model), strategies=rescue, max_crops=args.max_crops,
                                     dedupe=args.dedupe, crop_max_side=getattr(args, "crop_max_side", None), **options)
    else:
        detector = Detector(Path(args.model), **options)
    if getattr(args, "hand_detector", None):
        from .hybrid import HybridDetector
        detector = HybridDetector(detector, Path(args.model), Path(args.rtm_models), args.detection_threshold,
                                  args.presence_threshold, num_hands=args.num_hands)
    return detector


def process(args, progress=None, detector_override=None, started=None, extra_metrics=None):
    """Process one video interval into a run directory.

    ``progress``, if given, is called as ``progress(processed_frames, expected_frames)``
    about once per second of source video (expected is an estimate from timestamps,
    stride and limits) so a job runner can report status without parsing stdout.
    """
    started = time.perf_counter() if started is None else started
    source, out = Path(args.video), Path(args.out)
    if not source.is_file():
        raise FileNotFoundError(source)
    if not Path(args.model).is_file():
        raise FileNotFoundError("Model missing. Run: egohand fetch-model")
    if out.exists() and any(out.iterdir()):
        raise ValueError("Output directory is nonempty; choose a new --out directory")
    # Fail before any decoding if the governance file is invalid or already past retention.
    governance = load_governance(Path(args.governance) if getattr(args, "governance", None) else None,
                                 date.today())
    stages = {k: 0. for k in ["probe", "setup", "decode", "resize_convert", "detect",
                              "track", "frame_stats", "export_rows", "render_video", "rerun_log", "finalize"]}
    mark = time.perf_counter()
    info = probe(source, getattr(args, "timestamp_source", "auto"))
    stages["probe"] = time.perf_counter() - mark
    if not info["cfr"] and not args.no_video:
        raise ValueError("VFR input: use --no-video --rrd for exact-timestamp replay, or transcode to CFR")
    out.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(str(source))
    if not cap.isOpened():
        raise ValueError("OpenCV could not decode video")
    detector = video_sink = rerun_sink = None
    tracker = IdentityTracker(args.predict_seconds, args.retain_seconds, not args.no_smoothing,
                              (int(info["width"]), int(info["height"]))
                              if getattr(args, "tracker_units", "normalized") == "diagonal" else None,
                              box_link=bool(getattr(args, "box_link", False)),
                              side_weights=({"center_crop_rescue": args.crop_side_weight}
                                            if getattr(args, "crop_side_weight", None) is not None else None),
                              side_hysteresis=getattr(args, "side_hysteresis", None) or 0.)
    rss = psutil.Process()
    peak_rss = rss.memory_info().rss
    latency, sample_rows, events = [], [], []
    previous_states = {}
    counts = {"observed": 0, "reacquired": 0, "predicted": 0, "lost": 0, "retired": 0}
    observed_frames = processed = 0
    first_s = last_s = None
    best_poster_hands = -1
    try:
        mark = time.perf_counter()
        detector = detector_override if detector_override is not None else build_detector(args)
        preset = getattr(args, "preset", None)
        subtitle = ("FACTORY POV  /  MEDIAPIPE  /  " +
                    (f"PRESET {preset.upper()}" if preset else "CUSTOM SETTINGS") +
                    f"  (thresholds {args.detection_threshold:g}" +
                    (", centre-crop rescue)" if args.rescue_crop else
                     f", crops: {args.rescue})" if getattr(args, "rescue", None) else ", no crops)"))
        if not args.no_video:
            video_sink = VideoSink(out/"preview.mp4", info["fps"]/args.stride)
        if args.rrd:
            rerun_sink = RerunSink(out/"replay.rrd")
        stages["setup"] = time.perf_counter() - mark
        fields = ["frame_index", "timestamp_s", "track_id", "state", "observed", "side",
                  "handedness_score", "landmark_index", "x_norm", "y_norm", "z_norm",
                  "world_x_m", "world_y_m", "world_z_m", "raw_x_norm", "raw_y_norm",
                  "raw_z_norm", "raw_world_x_m", "raw_world_y_m", "raw_world_z_m", "missing_reason"]
        with (out/"landmarks.jsonl").open("w") as jf, (out/"landmarks.csv").open("w", newline="") as cf:
            writer = csv.DictWriter(cf, fieldnames=fields)
            writer.writeheader()
            frame_index = -1
            timestamps = info["timestamps"]
            relative = np.asarray(timestamps) - timestamps[0]
            in_range = (relative >= args.start_seconds) & (
                relative < args.start_seconds + args.duration if args.duration is not None else True)
            expected = int(np.count_nonzero(in_range)) // max(1, args.stride)
            if args.max_frames is not None:
                expected = min(expected, args.max_frames)
            while True:
                # Frames are always decoded sequentially so frame index <-> PTS stays
                # exact; frames before the interval or skipped by stride are grabbed
                # without the BGR conversion/copy.
                upcoming = frame_index + 1
                skip = upcoming < len(timestamps) and (
                    timestamps[upcoming] - timestamps[0] < args.start_seconds or upcoming % args.stride)
                mark = time.perf_counter()
                if skip:
                    ok, frame = cap.grab(), None
                else:
                    ok, frame = cap.read()
                stages["decode"] += time.perf_counter() - mark
                if not ok:
                    if args.duration is None and args.max_frames is None and frame_index+1 != len(timestamps):
                        raise RuntimeError("Decoded frame count does not match timestamp count")
                    break
                frame_index += 1
                if frame_index >= len(timestamps):
                    raise RuntimeError("Decoded frame count exceeds timestamp count")
                pts = timestamps[frame_index]
                timestamp = pts - timestamps[0]
                if skip:
                    if args.duration is not None and timestamp >= args.start_seconds + args.duration:
                        break
                    continue
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
                mark = time.perf_counter()
                resized = cv2.resize(frame, (round(w*scale), round(h*scale))) if scale < 1 else frame
                rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
                stages["resize_convert"] += time.perf_counter() - mark
                inference_start = time.perf_counter()
                detections = (detector.detect(rgb, timestamp, frame) if not isinstance(detector, Detector)
                              else detector.detect(rgb, timestamp))
                measured = time.perf_counter() - inference_start
                # Precomputed (parallel) detections report the worker's real inference time.
                latency.append(detector.reported_latency(timestamp, measured)
                               if hasattr(detector, "reported_latency") else measured)
                stages["detect"] += latency[-1]
                mark = time.perf_counter()
                hands = (tracker.update(detections, timestamp) if args.identity == "persistent"
                         else baseline_records(detections))
                stages["track"] += time.perf_counter() - mark
                mark = time.perf_counter()
                stages["export_rows"] += time.perf_counter() - mark
                mark = time.perf_counter()
                _, stats = frame_stats(frame)
                stages["frame_stats"] += time.perf_counter() - mark
                mark = time.perf_counter()
                sample = {"frame_index": frame_index, "timestamp_s": timestamp,
                          "source_pts_s": pts,
                          "quality": {"blur_laplacian_var": stats["blur_laplacian_var"],
                                      "mean_luma": stats["mean_luma"],
                                      "masks": {"hand_observed": any(h["observed"] for h in hands)}},
                          "hands": hands}
                jf.write(json.dumps(sample, separators=(",", ":"), allow_nan=False)+"\n")
                observed_frames += int(bool(detections))
                for hand in hands:
                    counts[hand["state"]] += 1
                    previous = previous_states.get(hand["track_id"])
                    if previous != hand["state"]:
                        events.append({"frame_index": frame_index, "timestamp_s": timestamp,
                                       "track_id": hand["track_id"], "side": hand["side"],
                                       "from_state": previous, "to_state": hand["state"],
                                       "missing_reason": hand.get("missing_reason")})
                    previous_states[hand["track_id"]] = hand["state"]
                    base = {k: sample[k] for k in ["frame_index", "timestamp_s"]}
                    base.update({k: hand[k] for k in ["track_id", "state", "observed", "side", "handedness_score"]})
                    base["missing_reason"] = hand.get("missing_reason")
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
                stages["export_rows"] += time.perf_counter() - mark
                mark = time.perf_counter()
                if video_sink:
                    rendered = composite(frame, sample, subtitle)
                    video_sink.write(rendered)
                    if len(detections) > best_poster_hands:
                        cv2.imwrite(str(out/"preview.jpg"), rendered)
                        best_poster_hands = len(detections)
                stages["render_video"] += time.perf_counter() - mark
                mark = time.perf_counter()
                if rerun_sink:
                    rerun_sink.write(resized, sample)
                stages["rerun_log"] += time.perf_counter() - mark
                processed += 1
                if progress is not None and processed % 30 == 0:
                    progress(processed, expected)
                first_s = timestamp if first_s is None else first_s
                last_s = timestamp
                peak_rss = max(peak_rss, rss.memory_info().rss)
                if processed % 100 == 0:
                    print(f"Processed {processed} frames; source time {timestamp:.2f}s", flush=True)
        if processed == 0:
            raise ValueError("No frames processed; check input and selected time range")
        finalize_start = time.perf_counter()
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
                            missing_reason=np.array([r[2].get("missing_reason") or "" for r in sample_rows], dtype="U16"),
                            observed=np.array([r[2]["observed"] for r in sample_rows], dtype=bool))
        peak_rss = max(peak_rss, rss.memory_info().rss)
        with (out/"tracking_events.csv").open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["frame_index", "timestamp_s", "track_id", "side", "from_state",
                                                   "to_state", "missing_reason"])
            writer.writeheader()
            writer.writerows(events)
        stages["finalize"] = time.perf_counter() - finalize_start
        elapsed = time.perf_counter() - started
        metrics = {
            "processed_frames": processed, "frames_with_observed_hands": observed_frames,
            "observed_frame_fraction": observed_frames/processed,
            "track_state_samples": counts,
            "track_ids_created": tracker.next_id-1 if args.identity == "persistent" else None,
            "reacquisitions": tracker.reacquisitions if args.identity == "persistent" else None,
            "box_links": tracker.box_links if args.identity == "persistent" else None,
            "ghosts_suppressed": tracker.ghosts_suppressed if args.identity == "persistent" else None,
            "first_timestamp_s": first_s, "last_timestamp_s": last_s,
            "processing_seconds": elapsed, "end_to_end_fps": processed/elapsed,
            **(extra_metrics or {}),
            "inference_seconds": sum(latency), "inference_fps": processed/sum(latency),
            "inference_p50_ms": float(np.percentile(latency, 50)*1000),
            "inference_p95_ms": float(np.percentile(latency, 95)*1000),
            "sampled_peak_process_rss_mb": peak_rss/1024**2,
            "stage_seconds": {k: round(v, 4) for k, v in stages.items()},
            "stage_seconds_unattributed": round(elapsed - sum(stages.values()), 4),
            "timestamp_source": info["timestamp_source"],
            "detector_stats": getattr(detector, "stats", None),
            "accuracy": None, "identity_switches": None,
            "notes": ["Coverage is not recall or accuracy; labels are required.",
                      "Reacquisitions are tracker decisions, not verified identity recovery.",
                      "RSS is sampled at frame/export boundaries and may miss short peaks.",
                      "End-to-end timing starts at process entry, includes probe, model setup, rendering, logging and exports; excludes interpreter/import startup and downloads.",
                      "NPZ has one row per track-state sample; missing values are NaN; JSONL retains empty frames."],
        }
        (out/"metrics.json").write_text(json.dumps(metrics, indent=2)+"\n")
        manifest = {
            "schema_version": "0.5",
            "frame_record_schema": "egohand_twin_frame.schema.json (package egohand_twin/schemas)", "created_utc": datetime.now(timezone.utc).isoformat(),
            "source": {"name": source.name, "sha256": sha256(source),
                       "width": int(info["width"]), "height": int(info["height"]),
                       "fps": info["fps"], "cfr": info["cfr"], "total_frames": len(info["timestamps"]),
                       "timestamp_source": info["timestamp_source"], "timestamp_note": info["timestamp_note"]},
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
            **governance,
        }
        (out/"manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")
        (out/"COMPLETE").write_text("Processing completed successfully.\n")
        if progress is not None:
            progress(processed, processed)
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
