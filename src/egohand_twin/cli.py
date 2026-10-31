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

from .evaluation import evaluate
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
    p.add_argument("--rescue-crop", action="store_true", help="Experimental center-crop rescue; evaluate false positives separately")
    p.add_argument("--no-smoothing", action="store_true")
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
    p.set_defaults(func=lambda a: rebuild_replay(Path(a.video), Path(a.run), Path(a.out)))
    p = commands.add_parser("evaluate", help="Score observed detections against manual labels")
    p.add_argument("run")
    p.add_argument("labels")
    p.add_argument("--wrist-threshold", type=float, default=.1)
    p.add_argument("--pck-threshold", type=float, default=.03)
    p.set_defaults(func=lambda a: print(json.dumps(evaluate(
        Path(a.run), Path(a.labels), a.wrist_threshold, a.pck_threshold), indent=2)))
    p = commands.add_parser("sample-labels", help="Create private annotation frames and an unlabeled template")
    p.add_argument("video")
    p.add_argument("--out", required=True)
    p.add_argument("--samples", type=int, default=12)
    p.add_argument("--start-seconds", type=float, default=0.)
    p.add_argument("--duration", type=float)
    p.set_defaults(func=sample_labels)
    args = parser.parse_args()
    for name in ["max_width", "stride", "max_frames", "duration", "num_hands", "samples", "wrist_threshold", "pck_threshold"]:
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
