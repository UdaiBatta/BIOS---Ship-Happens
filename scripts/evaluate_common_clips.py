"""Run repeatable, unlabeled coverage measurements on a shared set of clips.

Coverage describes what the processor emitted; it is not recall or accuracy.
All run artifacts and the per-clip summary belong under the private runs/ tree.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile

VIDEO_SUFFIXES = {".avi", ".m4v", ".mkv", ".mov", ".mp4", ".webm"}
PRESETS = ("baseline", "recall", "accurate", "hybrid")


def video_paths(inputs: list[Path]) -> list[Path]:
    paths = set()
    for item in inputs:
        if not item.exists():
            raise ValueError("An input path does not exist")
        if item.is_dir():
            paths.update(p.resolve() for p in item.rglob("*") if p.is_file() and p.suffix.lower() in VIDEO_SUFFIXES)
        elif item.is_file() and item.suffix.lower() in VIDEO_SUFFIXES:
            paths.add(item.resolve())
        else:
            raise ValueError("Input must be a video file or folder")
    if not paths:
        raise ValueError("No supported video files found")
    return sorted(paths, key=lambda p: (str(p).casefold(), str(p)))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _has_landmarks(hand: dict, key: str) -> bool:
    points = hand.get(key)
    return isinstance(points, list) and bool(points)


def summarize_run(run: Path) -> dict:
    """Summarize observed coverage directly from pipeline artifacts."""
    metrics = json.loads((run / "metrics.json").read_text())
    tracks: dict[int, str] = {}
    n_frames = observed_frames = observed_hands = predicted_2d = hands_2d = 0
    sides = {"Left": 0, "Right": 0, "unknown": 0}
    flips = transition_denominator = 0
    with (run / "landmarks.jsonl").open() as f:
        for line in f:
            frame = json.loads(line)
            n_frames += 1
            frame_observed = 0
            for hand in frame["hands"]:
                if _has_landmarks(hand, "image_xyz"):
                    hands_2d += 1
                    predicted_2d += hand.get("state") == "predicted"
                if not hand.get("observed"):
                    continue
                observed_hands += 1
                frame_observed += 1
                side = hand.get("side")
                side = side if side in ("Left", "Right") else "unknown"
                sides[side] += 1
                track = hand["track_id"]
                if track in tracks and side in ("Left", "Right") and tracks[track] in ("Left", "Right"):
                    transition_denominator += 1
                    flips += int(side != tracks[track])
                tracks[track] = side
            observed_frames += frame_observed > 0
    if not n_frames or n_frames != metrics["processed_frames"]:
        raise ValueError("landmarks frame count does not match metrics")

    result = {
        "processed_frames": n_frames,
        "observed_hand_frames": observed_frames,
        "observed_hand_frames_denominator": n_frames,
        "observed_hand_frame_share": observed_frames / n_frames,
        "observed_hands": observed_hands,
        "observed_hands_denominator_for_hands_per_frame": n_frames,
        "observed_hands_per_frame": observed_hands / n_frames,
        "observed_side_counts": sides,
        "observed_side_counts_denominator": observed_hands,
        "observed_side_shares": {side: count / observed_hands if observed_hands else None
                                  for side, count in sides.items()},
        "left_right_flips_inside_tracks": flips,
        "flip_transition_denominator": transition_denominator,
        "flip_share": flips / transition_denominator if transition_denominator else None,
        "predicted_2d_hands": predicted_2d,
        "predicted_2d_share_denominator": hands_2d,
        "predicted_2d_share": predicted_2d / hands_2d if hands_2d else None,
        "processing_seconds": metrics["processing_seconds"],
        "end_to_end_fps": metrics["end_to_end_fps"],
    }
    lift_files = sorted(run.glob("lift_*.npz"))
    if lift_files:
        import numpy as np
        with np.load(lift_files[0], allow_pickle=False) as lift:
            ok = lift["ok"].astype(bool)
        result["camera_space_lifted_share"] = {
            "status": "measured", "lifted": int(ok.sum()), "observed_hands_denominator": int(ok.size),
            "share": float(ok.mean()) if ok.size else None,
        }
    else:
        result["camera_space_lifted_share"] = "not measured"
    return result


def hybrid_available(repo: Path) -> bool:
    return hybrid_unavailable_reason(repo) is None


def hybrid_unavailable_reason(repo: Path) -> str | None:
    missing = [name for name in ("rtmdet_nano_hand.onnx", "rtmpose_m_hand.onnx")
               if not (repo / "models" / "rtm" / name).is_file()]
    if missing:
        return "missing RTM model files"
    try:
        runtime = importlib.import_module("onnxruntime")
        runtime.SessionOptions()
    except Exception as exc:
        return f"onnxruntime unavailable ({type(exc).__name__})"
    return None


def write_summary(path: Path, summary: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="summary-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)
            f.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _success(row: dict) -> bool:
    return row.get("status") == "complete" and isinstance(row.get("metrics"), dict)


def _set_overall_status(summary: dict) -> None:
    rows = [run for clip in summary["clips"] for run in clip.get("runs", {}).values()]
    failed = any(run.get("status") == "failed" for run in rows) or any(
        clip.get("status") == "failed" for clip in summary["clips"])
    completed = any(_success(run) for run in rows)
    summary["status"] = "partial" if failed and completed else "failed" if failed else "running"


def pooled_metrics(rows: list[dict]) -> dict:
    successful = [row["metrics"] for row in rows if _success(row)]
    if not successful:
        return {"clips_completed": 0}
    frames = sum(m["processed_frames"] for m in successful)
    hands = sum(m["observed_hands"] for m in successful)
    observed_frames = sum(m["observed_hand_frames"] for m in successful)
    sides = {side: sum(m["observed_side_counts"][side] for m in successful)
             for side in ("Left", "Right", "unknown")}
    pred_num = sum(m["predicted_2d_hands"] for m in successful)
    pred_den = sum(m["predicted_2d_share_denominator"] for m in successful)
    flip_num = sum(m["left_right_flips_inside_tracks"] for m in successful)
    flip_den = sum(m["flip_transition_denominator"] for m in successful)
    processing = sum(m["processing_seconds"] for m in successful)
    measured_lifts = [m["camera_space_lifted_share"] for m in successful
                      if isinstance(m["camera_space_lifted_share"], dict)]
    lift_num = sum(m["lifted"] for m in measured_lifts)
    lift_den = sum(m["observed_hands_denominator"] for m in measured_lifts)
    return {
        "clips_completed": len(successful), "processed_frames": frames,
        "observed_hand_frames": observed_frames, "observed_hand_frames_denominator": frames,
        "observed_hand_frame_share": observed_frames / frames if frames else None,
        "observed_hands": hands, "observed_hands_denominator_for_hands_per_frame": frames,
        "observed_hands_per_frame": hands / frames if frames else None,
        "observed_side_counts": sides, "observed_side_counts_denominator": hands,
        "observed_side_shares": {side: (count / hands if hands else None) for side, count in sides.items()},
        "left_right_flips_inside_tracks": flip_num, "flip_transition_denominator": flip_den,
        "predicted_2d_hands": pred_num, "predicted_2d_share_denominator": pred_den,
        "predicted_2d_share": pred_num / pred_den if pred_den else None,
        "camera_space_lifted_hands": lift_num, "camera_space_lifted_share_denominator": lift_den,
        "camera_space_lifted_share": lift_num / lift_den if lift_den else "not measured",
        "processing_seconds": processing,
        "end_to_end_fps": frames / processing if processing else None,
    }


def report_text(summary: dict) -> str:
    """Build a path-free, filename-free coverage report from private summary data."""
    status = summary["status"]
    lines = ["# Common clip coverage results", "",
             "Coverage shows processor output on these intervals. It is not recall or accuracy; those require reviewed labels.", "",
             "Observed counts include every detected hand. Wearer-only coverage is not measured because the pipeline has no wearer-versus-bystander classifier.", "",
             f"Run status: **{status}**", "",
             f"Requested clips: {summary['requested_clips']}; presets: {', '.join(summary['presets'])}.", "",
             "Camera-space lift uses the experimental assumed-lens estimate (150° HFOV); it is not calibrated depth. A skipped lift is shown as not measured.", "",
             "## Per clip", ""]
    for clip in summary["clips"]:
        interval = clip.get("selected_interval")
        interval_text = (f"{interval['start_seconds']:g}–{interval['end_seconds']:g}" if interval else "unknown")
        lines.extend([f"### {clip['clip_id']} — selected interval: {interval_text} s", "",
                      "| Preset | Status | Observed frames / frames | Observed hands / frames | Left / Right / unknown shares | Flips / eligible transitions | Predicted 2D / 2D hands | Camera lifted / observed hands | Processing seconds | FPS |",
                      "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|"])
        for preset in summary["presets"]:
            row = clip.get("runs", {}).get(preset, {"status": "pending"})
            m = row.get("metrics") or {}
            if _success(row):
                side = m["observed_side_counts"]
                lift = m["camera_space_lifted_share"]
                lift_text = (f"{lift['lifted']}/{lift['observed_hands_denominator']}"
                             if isinstance(lift, dict) else "not measured")
                values = [f"{m['observed_hand_frames']}/{m['observed_hand_frames_denominator']} = {m['observed_hand_frames']/m['observed_hand_frames_denominator']:.3f}",
                          f"{m['observed_hands']}/{m['observed_hands_denominator_for_hands_per_frame']} = {m['observed_hands_per_frame']:.3f}",
                          " / ".join(f"{side[s]}/{m['observed_side_counts_denominator']} = {side[s]/m['observed_side_counts_denominator']:.3f}"
                                     if m["observed_side_counts_denominator"] else f"{side[s]}/0 = —"
                                     for s in ("Left", "Right", "unknown")),
                          f"{m['left_right_flips_inside_tracks']}/{m['flip_transition_denominator']} = {m['left_right_flips_inside_tracks']/m['flip_transition_denominator']:.3f}" if m['flip_transition_denominator'] else "0/0 = —",
                          f"{m['predicted_2d_hands']}/{m['predicted_2d_share_denominator']} = {m['predicted_2d_share']:.3f}" if m["predicted_2d_share"] is not None else f"{m['predicted_2d_hands']}/0 = —",
                          f"{lift_text} = {lift['share']:.3f}" if isinstance(lift, dict) and lift["share"] is not None else lift_text,
                          f"{m['processing_seconds']:.2f}", f"{m['end_to_end_fps']:.2f}"]
            else:
                values = ["—"] * 8
            lines.append("| " + " | ".join([preset, row.get("status", "pending"), *values]) + " |")
            if row.get("reason"):
                lines.append(f"\n{clip['clip_id']} {preset}: {row['reason']}\n")
            if row.get("camera_lift_reason"):
                lines.append(f"\n{clip['clip_id']} {preset} camera-space lift: {row['camera_lift_reason']}\n")
    lines += ["", "## Pooled by preset", "",
              "Counts and denominators are summed across completed clips. FPS is total processed frames divided by summed processing seconds.", "",
              "| Preset | Completed clips | Observed frames / frames | Observed hands / frames | Left / Right / unknown / observed hands | Flips / eligible transitions | Predicted 2D / 2D hands | Camera lifted / measured observed hands | Processing seconds | FPS |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for preset in summary["presets"]:
        rows = [clip.get("runs", {}).get(preset, {}) for clip in summary["clips"]]
        m = pooled_metrics(rows)
        if not m["clips_completed"]:
            lines.append(f"| {preset} | 0 | — | — | — | — | — | not measured | — | — |")
            continue
        s = m["observed_side_counts"]
        lift = (f"{m['camera_space_lifted_hands']}/{m['camera_space_lifted_share_denominator']}"
                if m["camera_space_lifted_share_denominator"] else "not measured")
        lines.append("| " + " | ".join([preset, str(m["clips_completed"]),
            f"{m['observed_hand_frames']}/{m['observed_hand_frames_denominator']} = {m['observed_hand_frame_share']:.3f}",
            f"{m['observed_hands']}/{m['observed_hands_denominator_for_hands_per_frame']} = {m['observed_hands_per_frame']:.3f}",
            " / ".join(f"{s[k]}/{m['observed_side_counts_denominator']} = {m['observed_side_shares'][k]:.3f}"
                       if m["observed_side_counts_denominator"] else f"{s[k]}/0 = —"
                       for k in ("Left", "Right", "unknown")),
            f"{m['left_right_flips_inside_tracks']}/{m['flip_transition_denominator']} = {m['left_right_flips_inside_tracks']/m['flip_transition_denominator']:.3f}" if m['flip_transition_denominator'] else "0/0 = —",
            f"{m['predicted_2d_hands']}/{m['predicted_2d_share_denominator']} = {m['predicted_2d_share']:.3f}" if m["predicted_2d_share"] is not None else f"{m['predicted_2d_hands']}/0 = —",
            f"{lift} = {m['camera_space_lifted_share']:.3f}" if isinstance(m["camera_space_lifted_share"], float) else lift,
            f"{m['processing_seconds']:.2f}", f"{m['end_to_end_fps']:.2f}"]) + " |")
    lines.append("")
    return "\n".join(lines)


def write_report(path: Path, summary: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="common-clips-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(report_text(summary))
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def probe_duration(clip: Path) -> float:
    from egohand_twin.ffmpeg import require_tool
    command = [require_tool("ffprobe"), "-v", "error", "-show_entries", "format=duration",
               "-of", "default=noprint_wrappers=1:nokey=1", str(clip)]
    result = subprocess.run(command, capture_output=True, text=True, check=True)
    duration = float(result.stdout.strip())
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("video duration must be finite and positive")
    return duration


def selected_interval(source_duration: float, start: float | None, length: float | None) -> dict:
    if not math.isfinite(source_duration) or source_duration <= 0:
        raise ValueError("source duration must be finite and positive")
    if (start is None) != (length is None):
        raise ValueError("--start and --duration must be supplied together")
    if start is not None:
        if not math.isfinite(start) or not math.isfinite(length):
            raise ValueError("interval values must be finite")
        if start < 0 or length <= 0 or start >= source_duration:
            raise ValueError("requested interval is outside the clip")
        end = min(source_duration, start + length)
        return {"start_seconds": start, "end_seconds": end, "duration_seconds": end - start}
    end = min(source_duration, 30.) if source_duration > 180 else source_duration
    return {"start_seconds": 0., "end_seconds": end, "duration_seconds": end,
            "selection": "fixed 0:30 for source over 180 seconds" if source_duration > 180 else "whole clip"}


def _write_failure_logs(run: Path, stdout: str, stderr: str) -> None:
    run.mkdir(parents=True, exist_ok=True)
    (run / "stdout.log").write_text(stdout, encoding="utf-8", errors="replace")
    (run / "stderr.log").write_text(stderr, encoding="utf-8", errors="replace")


def measure_camera_lift(run: Path) -> dict:
    command = [sys.executable, "-m", "egohand_twin.cli", "lift", str(run), "--hfov", "150"]
    try:
        done = subprocess.run(command, capture_output=True, text=True)
    except OSError as exc:
        _write_failure_logs(run, "", str(exc))
        return {"status": "not measured", "reason": f"lift launch failed ({type(exc).__name__})"}
    if done.returncode:
        _write_failure_logs(run, done.stdout, done.stderr)
        return {"status": "not measured", "reason": "lift command failed"}
    try:
        import numpy as np
        sidecar = run / "lift_hfov150.npz"
        with np.load(sidecar, allow_pickle=False) as data:
            frames, tracks, ok = data["frame_index"], data["track_id"], data["ok"].astype(bool)
        expected = []
        with (run / "landmarks.jsonl").open() as f:
            for line in f:
                frame = json.loads(line)
                expected.extend((frame["frame_index"], hand["track_id"])
                                for hand in frame["hands"] if hand.get("observed"))
        actual = list(zip(frames.tolist(), tracks.tolist()))
        if actual != expected or len(ok) != len(expected):
            raise ValueError("lift sidecar does not match the run's observed records")
        denominator = len(ok)
        return {"status": "measured", "lifted": int(ok.sum()),
                "observed_hands_denominator": denominator,
                "share": float(ok.mean()) if denominator else None,
                "method": "experimental assumed 150-degree HFOV PnP"}
    except Exception:
        return {"status": "not measured", "reason": "lift sidecar failed run-bound validation"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", type=Path, help="Video files and/or folders (searched recursively)")
    parser.add_argument("--presets", nargs="+", choices=PRESETS,
                        help="Presets to run (default: baseline, recall, accurate, plus hybrid when ready)")
    parser.add_argument("--start", type=float, help="Explicit shared interval start in seconds; requires --duration")
    parser.add_argument("--duration", type=float, help="Explicit shared interval length in seconds; requires --start")
    parser.add_argument("--workers", type=int, default=1, help="Detection workers per run (default: 1)")
    parser.add_argument("--out", type=Path, default=Path("runs/common"), help="Private output folder")
    parser.add_argument("--report", type=Path, default=Path("docs/COMMON_CLIPS_RESULTS.md"),
                        help="Aggregate report (contains neutral IDs and metrics only)")
    args = parser.parse_args(argv)
    if args.workers < 1:
        parser.error("--workers must be positive")
    if (args.start is None) != (args.duration is None):
        parser.error("--start and --duration must be supplied together")
    if args.start is not None and (not math.isfinite(args.start) or not math.isfinite(args.duration)
                                   or args.start < 0 or args.duration <= 0):
        parser.error("--start and --duration must be finite; start nonnegative and duration positive")
    try:
        clips = video_paths(args.inputs)
    except ValueError as exc:
        parser.error(str(exc))
    hybrid_ready = hybrid_available(Path.cwd())
    hybrid_reason = None if hybrid_ready else hybrid_unavailable_reason(Path.cwd())
    presets = list(dict.fromkeys(args.presets or list(PRESETS)))
    out = args.out.resolve()
    summary_path = out / "summary.json"
    summary = {"status": "running", "requested_clips": len(clips), "presets": presets, "workers": args.workers,
               "hybrid_skip_reason": hybrid_reason, "clips": []}
    # Refuse to reuse output IDs; each invocation needs fresh artifacts to avoid stale comparisons.
    if out.exists() and any(out.iterdir()):
        parser.error("output run folder already exists; choose a fresh --out folder")

    def persist() -> None:
        write_summary(summary_path, summary)
        write_report(args.report, summary)

    for index, clip in enumerate(clips, 1):
        clip_row = {"clip_id": f"C{index}", "source_sha256": sha256(clip), "status": "queued", "runs": {}}
        summary["clips"].append(clip_row)
        try:
            source_duration = probe_duration(clip)
            interval = selected_interval(source_duration, args.start, args.duration)
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            clip_row.update(status="failed", reason=f"input duration unavailable ({type(exc).__name__})")
            for preset in presets:
                clip_row["runs"][preset] = {"status": "failed", "reason": clip_row["reason"]}
            _set_overall_status(summary)
            persist()
            print(f"Could not determine duration for {clip_row['clip_id']}", file=sys.stderr)
            return 1
        clip_row.update(status="processing", source_duration_seconds=source_duration,
                        selected_interval=interval)
        persist()
        for preset in presets:
            run = out / f"C{index}" / preset
            row = {"status": "queued"}
            clip_row["runs"][preset] = row
            if preset == "hybrid" and not hybrid_ready:
                row.update(status="skipped", reason=hybrid_reason or "hybrid runtime unavailable")
                persist()
                continue
            row["status"] = "processing"
            persist()
            command = [sys.executable, "-m", "egohand_twin.cli", "process", str(clip), "--out", str(run),
                       "--preset", preset, "--start-seconds", str(interval["start_seconds"]),
                       "--workers", str(args.workers), "--no-video"]
            if interval["duration_seconds"] < source_duration:
                command.extend(["--duration", str(interval["duration_seconds"])])
            try:
                done = subprocess.run(command, capture_output=True, text=True)
            except OSError as exc:
                _write_failure_logs(run, "", str(exc))
                row.update(status="failed", reason=f"process launch failed ({type(exc).__name__})")
                clip_row["status"] = "partial"
                _set_overall_status(summary)
                persist()
                print(f"Processing failed for {clip_row['clip_id']} ({preset})", file=sys.stderr)
                return 1
            if done.returncode:
                _write_failure_logs(run, done.stdout, done.stderr)
                row.update(status="failed", reason=f"process exited with code {done.returncode}")
                clip_row["status"] = "partial"
                _set_overall_status(summary)
                persist()
                print(f"Processing failed for {clip_row['clip_id']} ({preset}); private artifacts retained", file=sys.stderr)
                return done.returncode or 1
            try:
                metrics = summarize_run(run)
                lift = measure_camera_lift(run)
                metrics["camera_space_lifted_share"] = lift if lift["status"] == "measured" else "not measured"
                if lift["status"] != "measured":
                    row["camera_lift_reason"] = lift["reason"]
                row.update(status="complete", metrics=metrics)
            except (OSError, KeyError, ValueError, json.JSONDecodeError) as exc:
                _write_failure_logs(run, done.stdout, done.stderr)
                row.update(status="failed", reason=f"artifact summary failed ({type(exc).__name__})")
                clip_row["status"] = "partial"
                _set_overall_status(summary)
                persist()
                print(f"Could not summarize {clip_row['clip_id']} ({preset})", file=sys.stderr)
                return 1
            persist()
        clip_row["status"] = "complete" if all(r["status"] in ("complete", "skipped")
                                                for r in clip_row["runs"].values()) else "partial"
        persist()
    failed = any(run.get("status") == "failed" for clip in summary["clips"]
                 for run in clip.get("runs", {}).values()) or any(c.get("status") == "failed" for c in summary["clips"])
    completed = any(_success(run) for clip in summary["clips"] for run in clip.get("runs", {}).values())
    summary["status"] = ("partial" if failed and completed else "failed" if failed else
                         "complete" if completed else "skipped")
    persist()
    print(f"Processed {sum(1 for c in summary['clips'] for r in c['runs'].values() if _success(r))} clip-preset runs; private summary and aggregate report saved.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
