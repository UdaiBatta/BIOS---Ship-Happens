from __future__ import annotations

import argparse
import importlib.metadata
import json
from pathlib import Path
import platform
import shutil
import sys

import cv2
import numpy as np
import psutil

from .annotate import make_annotation_set, parse_intervals
from .evaluation import evaluate
from .identity import write_identity
from .lift import hand_relative_variation, lift_run
from .model import fetch_model, sha256
from .pipeline import probe, process
from .render import fit_image, text, rebuild_replay


def doctor(args):
    packages = {}
    for name in ["mediapipe", "opencv-python", "opencv-contrib-python", "numpy", "scipy", "rerun-sdk"]:
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    print(json.dumps({"platform": platform.platform(), "machine": platform.machine(),
                      "python": platform.python_version(), "logical_cpus": psutil.cpu_count(),
                      "ram_gb": round(psutil.virtual_memory().total/1024**3, 2),
                      "backend": "MediaPipe CPU (GPU acceleration not assumed)",
                      "ffmpeg": shutil.which("ffmpeg"), "ffprobe": shutil.which("ffprobe"),
                      "packages": packages}, indent=2))


def sample_labels(args):
    source, out = Path(args.video), Path(args.out)
    if out.exists() and any(out.iterdir()):
        raise ValueError("Choose an empty annotation output directory")
    info = probe(source)
    out.mkdir(parents=True, exist_ok=True)
    relative = np.asarray(info["timestamps"])-info["timestamps"][0]
    eligible = np.flatnonzero((relative >= args.start_seconds) &
                             (relative < args.start_seconds + args.duration if args.duration is not None
                              else np.ones(len(relative), dtype=bool)))
    if not len(eligible):
        raise ValueError("No frames in requested annotation interval")
    indices = eligible[np.unique(np.linspace(0, len(eligible)-1, args.samples, dtype=int))]
    cap = cv2.VideoCapture(str(source))
    sheet = np.zeros((int(np.ceil(len(indices)/3))*250, 3*400, 3), np.uint8)
    frames = []
    for n, index in enumerate(indices):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(index))
        ok, image = cap.read()
        if not ok:
            raise ValueError(f"Could not read annotation frame {index}")
        cv2.imwrite(str(out/f"frame_{index:06}.jpg"), image)
        small = fit_image(image, 400, 225)
        x, y = (n % 3)*400, (n//3)*250
        sheet[y:y+225, x:x+400] = small
        text(sheet, f"frame {index} / {info['timestamps'][index]-info['timestamps'][0]:.2f}s", x+8, y+245, .5)
        frames.append({"frame_index": int(index), "hands": []})
    cap.release()
    cv2.imwrite(str(out/"contact_sheet.jpg"), sheet)
    template = {"source_sha256": sha256(source), "reviewed": False,
                "instructions": "UNLABELED TEMPLATE. Add ALL visible labelable hands; empty hands means no visible hands. Each hand needs identity and normalized wrist_xy; optional landmarks_xy has 21 xy/null entries. Do not evaluate this template unchanged.",
                "frames": frames}
    (out/"labels.template.json").write_text(json.dumps(template, indent=2)+"\n")
    print(out/"contact_sheet.jpg")


def evaluate_command(a):
    result = evaluate(Path(a.run), Path(a.labels), a.wrist_threshold, a.pck_threshold,
                      a.allow_provisional, split=a.split)
    if a.summary:
        result = {k: v for k, v in result.items() if k not in ("false_positive_predictions", "missed_hands")}
    print(json.dumps(result, indent=2))


def main():
    parser = argparse.ArgumentParser(description="EgoHand Twin: offline 3D hand landmark reconstruction")
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("doctor", help="Inspect this machine and installed dependencies")
    p.set_defaults(func=doctor)
    p = commands.add_parser("fetch-model", help="Download the versioned official MediaPipe task model")
    p.add_argument("--model", default="models/hand_landmarker.task")
    p.set_defaults(func=lambda a: print(json.dumps(fetch_model(Path(a.model)), indent=2)))
    p = commands.add_parser("process", help="Export landmarks and synchronized replay")
    p.add_argument("video")
    p.add_argument("--out", required=True)
    p.add_argument("--model", default="models/hand_landmarker.task")
    p.add_argument("--max-width", type=int, default=960)
    p.add_argument("--stride", type=int, default=1)
    p.add_argument("--max-frames", type=int)
    p.add_argument("--start-seconds", type=float, default=0.)
    p.add_argument("--duration", type=float)
    p.add_argument("--num-hands", type=int, default=2)
    p.add_argument("--identity", choices=["persistent", "baseline"], default="persistent")
    p.add_argument("--detector-mode", choices=["video", "image"], default="video")
    p.add_argument("--rescue-crop", action="store_true", help="Historical center-crop rescue on the downscaled frame (wrist dedupe)")
    p.add_argument("--rescue", help="Experimental full-resolution crop strategies, comma-separated: guided,center,tiles")
    p.add_argument("--max-crops", type=int, default=4, help="Maximum crop proposals evaluated per frame")
    p.add_argument("--crop-max-side", type=int, help="Area-downscale each rescue crop to at most this many pixels")
    p.add_argument("--dedupe", choices=["landmarks", "wrist"], default="landmarks",
                   help="Duplicate rule for --rescue candidates")
    p.add_argument("--timestamp-source", choices=["auto", "frames"], default="auto",
                   help="auto: verified packet PTS (fast); frames: decode every frame with FFprobe")
    p.add_argument("--no-smoothing", action="store_true")
    p.add_argument("--tracker-units", choices=["normalized", "diagonal"], default="normalized",
                   help="Association distance units; diagonal is aspect-ratio correct")
    p.add_argument("--predict-seconds", type=float, default=.15)
    p.add_argument("--retain-seconds", type=float, default=.8)
    p.add_argument("--detection-threshold", type=float, default=.5)
    p.add_argument("--presence-threshold", type=float, default=.5)
    p.add_argument("--tracking-threshold", type=float, default=.5)
    p.add_argument("--no-video", action="store_true")
    p.add_argument("--rrd", action="store_true", help="Write synchronized Rerun recording")
    p.set_defaults(func=process)
    p = commands.add_parser("replay", help="Rebuild Rerun replay from cached landmarks without inference")
    p.add_argument("video")
    p.add_argument("run")
    p.add_argument("--out", required=True, help="New .rrd output filename")
    p.add_argument("--lift", help="Optional lift_*.npz from 'egohand lift' for an experimental camera-space view")
    p.set_defaults(func=lambda a: rebuild_replay(Path(a.video), Path(a.run), Path(a.out),
                                                 Path(a.lift) if a.lift else None))
    p = commands.add_parser("evaluate", help="Score observed detections against manual labels")
    p.add_argument("run")
    p.add_argument("labels")
    p.add_argument("--wrist-threshold", type=float, default=.1)
    p.add_argument("--pck-threshold", type=float, default=.03)
    p.add_argument("--allow-provisional", action="store_true",
                   help="Score unreviewed v2 labels; results are stamped provisional")
    p.add_argument("--summary", action="store_true", help="Omit per-frame miss/false-positive lists")
    p.add_argument("--split", help="Only score frames from this label split (e.g. dev or holdout)")
    p.set_defaults(func=evaluate_command)
    p = commands.add_parser("identity", help="Offline whole-track left/right vote -> RUN/identity.json")
    p.add_argument("run")
    p.add_argument("--margin", type=float, default=.15)
    p.add_argument("--min-observed", type=int, default=3)
    p.set_defaults(func=lambda a: print(write_identity(Path(a.run), a.margin, a.min_observed)))
    p = commands.add_parser("lift", help="EXPERIMENTAL camera-space PnP under an assumed fisheye lens")
    p.add_argument("run")
    p.add_argument("--hfov", type=float, nargs="+", default=[150.],
                   help="Assumed horizontal field(s) of view in degrees; several values give a sensitivity sweep")
    p.add_argument("--max-reproj-px", type=float, default=25.)
    p.set_defaults(func=lambda a: print(json.dumps({
        "hand_relative_bone_variation": hand_relative_variation(Path(a.run)),
        "lifts": {str(h): lift_run(Path(a.run), h, max_reproj_px=a.max_reproj_px) for h in a.hfov}}, indent=2)))
    p = commands.add_parser("sample-labels", help="Create private annotation frames and an unlabeled template")
    p.add_argument("video")
    p.add_argument("--out", required=True)
    p.add_argument("--samples", type=int, default=12)
    p.add_argument("--start-seconds", type=float, default=0.)
    p.add_argument("--duration", type=float)
    p.set_defaults(func=sample_labels)
    p = commands.add_parser("annotation-set", help="Split-aware frames, grid sheets and a v2 label template")
    p.add_argument("video")
    p.add_argument("--out", required=True)
    p.add_argument("--intervals", required=True, help="Comma-separated start:end seconds, e.g. 0:12,20:30")
    p.add_argument("--split", choices=["dev", "holdout"], required=True)
    p.add_argument("--step-frames", type=int, default=15)
    p.set_defaults(func=lambda a: print(len(make_annotation_set(
        Path(a.video), Path(a.out), probe(Path(a.video))["timestamps"],
        parse_intervals(a.intervals), a.step_frames, a.split)["frames"]), "frames"))
    args = parser.parse_args()
    for name in ["max_width", "stride", "max_frames", "duration", "num_hands", "samples", "step_frames", "max_crops", "crop_max_side", "wrist_threshold", "pck_threshold"]:
        if hasattr(args, name) and getattr(args, name) is not None and getattr(args, name) <= 0:
            parser.error(f"{name.replace('_', '-')} must be positive")
    if getattr(args, "start_seconds", 0) < 0:
        parser.error("start-seconds must be nonnegative")
    for name in ["detection_threshold", "presence_threshold", "tracking_threshold"]:
        if hasattr(args, name) and not 0 <= getattr(args, name) <= 1:
            parser.error(f"{name} must be between 0 and 1")
    try:
        args.func(args)
    except (ValueError, FileNotFoundError, RuntimeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
