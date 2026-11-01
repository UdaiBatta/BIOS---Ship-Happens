"""Render private cached MP4 handoff files for the common clip set."""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

import cv2

from motioniq.ffmpeg import require_tool
from motioniq.render import VideoSink, composite


ROOT = Path(__file__).resolve().parent.parent
PRESETS = ("baseline", "recall", "accurate", "hybrid")
DEFAULT_SUMMARY = ROOT / "runs" / "common" / "summary.json"
DEFAULT_VIDEOS = ROOT / "Media" / "Sample"
DEFAULT_OUTPUT = ROOT / "deliverables" / "drive"


def load_evaluator():
    path = Path(__file__).resolve().with_name("evaluate_common_clips.py")
    spec = importlib.util.spec_from_file_location("evaluate_common_clips", path)
    if spec is None or spec.loader is None:
        raise ValueError("common clip evaluator is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected a JSON object")
    return value


def iter_landmarks(path: Path):
    previous_index = -1
    count = 0
    with path.open(encoding="utf-8") as source:
        for line in source:
            if not line.strip():
                continue
            record = json.loads(line)
            if not isinstance(record, dict) or not isinstance(record.get("hands"), list):
                raise ValueError("invalid landmark frame")
            if isinstance(record.get("frame_index"), bool) or not isinstance(record.get("frame_index"), int):
                raise ValueError("invalid landmark frame index")
            timestamp = record.get("timestamp_s")
            if isinstance(timestamp, bool) or not isinstance(timestamp, (int, float)) or not math.isfinite(timestamp):
                raise ValueError("invalid landmark timestamp")
            if record["frame_index"] <= previous_index:
                raise ValueError("landmark frames are not in source order")
            previous_index = record["frame_index"]
            count += 1
            yield record
    if not count:
        raise ValueError("cached run has no landmark frames")


def load_landmarks(path: Path) -> list[dict]:
    return list(iter_landmarks(path))


def match_videos(video_inputs: list[Path], clips: list[dict], evaluator) -> list[tuple[Path, dict]]:
    paths = evaluator.video_paths(video_inputs)
    if len(paths) != len(clips):
        raise ValueError("video set does not match the cached summary")
    by_hash: dict[str, list[dict]] = {}
    seen_ids = set()
    for clip in clips:
        clip_id, source_hash = clip.get("clip_id"), clip.get("source_sha256")
        if not isinstance(clip_id, str) or not re.fullmatch(r"C[1-9]\d*", clip_id) or clip_id in seen_ids:
            raise ValueError("summary clip IDs are invalid or duplicated")
        if not isinstance(source_hash, str) or len(source_hash) != 64:
            raise ValueError("summary source hash is invalid")
        seen_ids.add(clip_id)
        by_hash.setdefault(source_hash.lower(), []).append(clip)

    matched = []
    for video in paths:
        source_hash = evaluator.sha256(video).lower()
        rows = by_hash.get(source_hash)
        if not rows:
            raise ValueError("video source hash does not match the cached summary")
        matched.append((video, rows.pop(0)))
    if any(rows for rows in by_hash.values()):
        raise ValueError("cached summary contains unmatched videos")
    return matched


def prepare_task(video: Path, clip: dict, summary_dir: Path, preset: str) -> dict:
    clip_id = clip["clip_id"]
    row = clip.get("runs", {}).get(preset, {})
    if row.get("status") != "complete" or not isinstance(row.get("metrics"), dict):
        raise ValueError("cached run is not complete")
    run_dir = summary_dir / clip_id / preset
    if not (run_dir / "COMPLETE").is_file():
        raise ValueError("cached run completion marker is missing")
    manifest = read_json(run_dir / "manifest.json")
    if manifest.get("source", {}).get("sha256", "").lower() != clip["source_sha256"].lower():
        raise ValueError("cached run source hash does not match the summary")
    parameters = manifest.get("parameters") or {}
    if parameters.get("preset") != preset:
        raise ValueError("cached run preset does not match the requested preset")
    stride = parameters.get("stride")
    if isinstance(stride, bool) or stride != 1:
        raise ValueError("cached run stride must be 1")

    frame_count = sum(1 for _ in iter_landmarks(run_dir / "landmarks.jsonl"))
    metrics = row["metrics"]
    if metrics.get("processed_frames") != frame_count:
        raise ValueError("cached frame count does not match its summary")
    if manifest.get("source", {}).get("cfr") is not True:
        raise ValueError("cached source must have verified constant frame rate for this renderer")
    source_fps = manifest.get("source", {}).get("fps")
    if isinstance(source_fps, bool) or not isinstance(source_fps, (int, float)) or not math.isfinite(source_fps) or source_fps <= 0:
        raise ValueError("cached source frame rate is invalid")
    interval = clip.get("selected_interval")
    if not isinstance(interval, dict):
        raise ValueError("cached interval is missing")
    start, end = interval.get("start_seconds"), interval.get("end_seconds")
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
           for value in (start, end)) or start < 0 or end <= start:
        raise ValueError("cached interval is invalid")
    processing_seconds = metrics.get("processing_seconds")
    if isinstance(processing_seconds, bool) or not isinstance(processing_seconds, (int, float)) or not math.isfinite(processing_seconds) or processing_seconds < 0:
        raise ValueError("cached processing time is invalid")
    observed_frames = metrics.get("observed_hand_frames")
    observed_hands = metrics.get("observed_hands")
    if any(isinstance(value, bool) or not isinstance(value, int) or value < 0
           for value in (observed_frames, observed_hands)) or observed_frames > frame_count:
        raise ValueError("cached coverage counts are invalid")
    return {"clip_id": clip_id, "video": video, "run_dir": run_dir, "frame_count": frame_count,
            "fps": float(source_fps), "interval": (float(start), float(end)),
            "processing_seconds": float(processing_seconds), "observed_frames": observed_frames,
            "observed_hands": observed_hands}


def load_task(metadata: dict) -> dict:
    """Load just one clip's cached landmarks after the batch metadata preflight."""
    task = dict(metadata)
    task["records"] = load_landmarks(task["run_dir"] / "landmarks.jsonl")
    if len(task["records"]) != task["frame_count"]:
        raise ValueError("cached frame count changed after preflight")
    return task


def encoded_info(path: Path) -> dict:
    command = [require_tool("ffprobe"), "-v", "error", "-select_streams", "v:0", "-count_packets",
               "-show_entries", "stream=codec_name,pix_fmt,duration,nb_read_packets:format=duration",
               "-of", "json", str(path)]
    result = subprocess.run(command, capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def validate_encoded(info: dict, expected_frames: int) -> None:
    streams = info.get("streams") or []
    if not streams:
        raise ValueError("encoded video has no video stream")
    stream = streams[0]
    if stream.get("codec_name") != "h264" or stream.get("pix_fmt") != "yuv420p":
        raise ValueError("encoded video codec or pixel format is incorrect")
    try:
        frames = int(stream["nb_read_packets"])
        duration_value = stream.get("duration")
        if not duration_value or duration_value == "N/A":
            duration_value = info.get("format", {}).get("duration")
        duration = float(duration_value)
    except (KeyError, TypeError, ValueError):
        raise ValueError("encoded video frame count or duration is missing") from None
    if frames != expected_frames or not math.isfinite(duration) or duration <= 0:
        raise ValueError("encoded video frame count or duration is invalid")


def publish_file(temporary: Path, target: Path) -> None:
    if os.name == "nt":
        os.rename(temporary, target)  # Windows rename fails if target already exists.
    else:
        os.link(temporary, target)  # portable no-clobber publication on the same filesystem
        temporary.unlink()


def ensure_outputs_unused(targets: list[Path], readme: Path) -> None:
    if readme.exists() or any(path.exists() for path in targets):
        raise ValueError("deliverable output already exists; choose an empty destination")


def render_task(task: dict, output_dir: Path, preset: str) -> dict:
    clip_id = task["clip_id"]
    target = output_dir / f"{clip_id}_{preset}.mp4"
    fd, temporary_name = tempfile.mkstemp(prefix=f".{clip_id}_{preset}-", suffix=".tmp.mp4", dir=output_dir)
    os.close(fd)
    temporary = Path(temporary_name)
    capture = cv2.VideoCapture(str(task["video"]))
    sink = None
    started = time.monotonic()
    try:
        if not capture.isOpened():
            raise ValueError("source video could not be decoded")
        sink = VideoSink(temporary, task["fps"])
        current_index = 0
        subtitle = f"{clip_id} / {preset} / labels not reviewed / estimated 3D"
        for sample in task["records"]:
            target_index = sample["frame_index"]
            if target_index < current_index:
                raise ValueError("landmark frame index is out of source order")
            frame = None
            while current_index <= target_index:
                ok, frame = capture.read()
                if not ok:
                    raise ValueError("source ended before a cached frame")
                current_index += 1
            sink.write(composite(frame, sample, subtitle=subtitle))
    finally:
        capture.release()
        if sink is not None:
            sink.close()

    render_seconds = time.monotonic() - started
    validate_encoded(encoded_info(temporary), len(task["records"]))
    publish_file(temporary, target)
    return {"filename": target.name, "bytes": target.stat().st_size, "render_seconds": render_seconds}


def write_readme(path: Path, preset: str, results: list[tuple[dict, dict]]) -> None:
    lines = [
        "MOTIONIQ common-clip review renders",
        "",
        f"Selected preset: {preset}. This selection is explicit and does not claim the preset is best.",
        "Label status: not reviewed. Accuracy is not measured by these renders.",
        "Coverage counts describe cached processor output, not recall or accuracy.",
        "Pipeline processing time is from the cached run; render time is measured separately here.",
        "3D is an estimate. It is hand-relative; factory position and camera motion are not reconstructed.",
        "",
        "| Clip ID | Preset | Interval (s) | Frames | Observed-hand frames | Observed hands | Pipeline processing (s, cached) | Render (s) | File bytes |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for task, output in results:
        start, end = task["interval"]
        lines.append(f"| {task['clip_id']} | {preset} | {start:g}–{end:g} | {task['frame_count']} | "
                     f"{task['observed_frames']} | {task['observed_hands']} | {task['processing_seconds']:.2f} | "
                     f"{output['render_seconds']:.2f} | {output['bytes']} |")
    with path.open("x", encoding="utf-8") as destination:
        destination.write("\n".join(lines) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--videos", type=Path, default=DEFAULT_VIDEOS)
    parser.add_argument("--preset", choices=PRESETS, default="accurate")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    tasks = []
    results = []
    rendering = False
    try:
        evaluator = load_evaluator()
        summary = read_json(args.summary)
        clips = summary.get("clips")
        if not isinstance(clips, list) or not clips:
            raise ValueError("cached summary has no clips")
        matched = match_videos([args.videos], clips, evaluator)
        tasks = [prepare_task(video, clip, args.summary.resolve().parent, args.preset)
                 for video, clip in matched]
        output_dir = args.out.resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        targets = [output_dir / f"{task['clip_id']}_{args.preset}.mp4" for task in tasks]
        readme = output_dir / "README.txt"
        ensure_outputs_unused(targets, readme)
        for task in tasks:
            rendering = True
            loaded = load_task(task)
            output = render_task(loaded, output_dir, args.preset)
            results.append((task, output))
            del loaded
            rendering = False
        write_readme(readme, args.preset, results)
    except Exception as exc:
        if results:
            print(f"Partial handoff: {len(results)} of {len(tasks)} clips rendered; completed MP4s were retained and the README was not written.",
                  file=sys.stderr)
        if rendering:
            print("Any temporary file from the failed clip was retained locally.", file=sys.stderr)
        print(f"Render failed: {type(exc).__name__}", file=sys.stderr)
        return 1
    print(f"Rendered {len(results)} cached clips for the selected preset.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
