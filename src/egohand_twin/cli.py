from __future__ import annotations

import argparse
from datetime import date
import importlib.metadata
import json
from pathlib import Path
import platform
import shutil
import sys

import cv2
import numpy as np
import psutil

from .annotate import apply_label_review, label_review_pack, make_annotation_set, parse_intervals
from .evaluation import evaluate
from .identity import write_identity, write_identity_jsonl
from .schema import validate_jsonl
from .lift import hand_relative_variation, lift_run
from .compare import compare
from .conditions import apply_conditions, template as conditions_template
from .governance import retention_report, template as governance_template
from .steps import load_steps, write_template
from .quality import assess, evaluate_quality, export_segments, write_quality
from .model import fetch_model, sha256
from .parallel import process_parallel
from .pipeline import probe
from .render import fit_image, text, rebuild_replay


PRESETS = {
    "baseline": {"detection_threshold": .5, "presence_threshold": .5, "tracking_threshold": .5, "rescue_crop": False},
    "recall": {"detection_threshold": .3, "presence_threshold": .3, "tracking_threshold": .3, "rescue_crop": True, "box_link": True},
    # recall + a second, reverse-time detection pass (offline only; about 2x detector time).
    "accurate": {"detection_threshold": .3, "presence_threshold": .3, "tracking_threshold": .3, "rescue_crop": True, "box_link": True,
                 "bidirectional": True},
    # recall + an RTMDet hand detector for hands MediaPipe's palm detector misses (needs fetch-model --rtm).
    "hybrid": {"detection_threshold": .3, "presence_threshold": .3, "tracking_threshold": .3, "rescue_crop": True, "box_link": True,
               "hand_detector": True},
}


def apply_preset(args):
    """Fill unset detector options from the preset; explicitly given flags win."""
    for key, value in PRESETS[args.preset].items():
        if getattr(args, key, None) is None:
            # An explicit --rescue strategy replaces the preset's historical centre crop.
            setattr(args, key, False if key == "rescue_crop" and getattr(args, "rescue", None) else value)
    return args


def mediapipe_runtime() -> str:
    """Check that MediaPipe's native library loads (on Linux it needs libGLESv2/libEGL)."""
    try:
        from mediapipe.tasks.python.core import mediapipe_c_bindings
        mediapipe_c_bindings.load_raw_library()
        return "ok"
    except Exception as error:  # report, do not crash the diagnostic
        hint = " (Debian/Ubuntu: sudo apt-get install libgles2 libegl1)" if "GL" in str(error) else ""
        return f"FAILED: {error}{hint}"


def doctor(args):
    packages = {}
    for name in ["mediapipe", "opencv-python", "opencv-contrib-python", "numpy", "scipy", "jsonschema", "rerun-sdk"]:
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    print(json.dumps({"platform": platform.platform(), "machine": platform.machine(),
                      "python": platform.python_version(), "logical_cpus": psutil.cpu_count(),
                      "ram_gb": round(psutil.virtual_memory().total/1024**3, 2),
                      "backend": "MediaPipe CPU (GPU acceleration not assumed)",
                      "ffmpeg": shutil.which("ffmpeg"), "ffprobe": shutil.which("ffprobe"),
                      "packages": packages, "mediapipe_runtime": mediapipe_runtime(),
                      "notes": ["Disable Rerun usage analytics for offline use: uv run rerun analytics disable"]},
                     indent=2))


def identity_command(args):
    run = Path(args.run)
    outputs = [run/"identity.json"] + ([run/"landmarks.identity.jsonl"] if args.write_jsonl else [])
    existing = [str(path.name) for path in outputs if path.exists()]
    if existing:
        raise ValueError(f"output exists; never overwritten: {', '.join(existing)}")
    paths = [write_identity(run, args.margin, args.min_observed)]
    if args.write_jsonl:
        paths.append(write_identity_jsonl(run, args.margin, args.min_observed))
    print("\n".join(map(str, paths)))


def lift_command(args):
    run = Path(args.run)
    if any(not 10 < h < 240 for h in args.hfov):
        raise ValueError("hfov_deg must be between 10 and 240")
    tags = [f"hfov{int(round(h))}" for h in args.hfov]
    outputs = [run/f"lift_{tag}.{ext}" for tag in tags for ext in ("npz", "json")]
    existing = [path.name for path in outputs if path.exists()]
    if len(tags) != len(set(tags)):
        raise ValueError("HFOV values produce duplicate lift output names")
    if existing:
        raise ValueError(f"output exists; never overwritten: {', '.join(existing)}")
    print(json.dumps({
        "hand_relative_bone_variation": hand_relative_variation(run),
        "lifts": {str(h): lift_run(run, h, max_reproj_px=args.max_reproj_px) for h in args.hfov}}, indent=2))


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
                      a.allow_provisional, split=a.split,
                      conditions=Path(a.conditions) if a.conditions else None)
    if a.summary:
        result = {k: v for k, v in result.items() if k not in ("false_positive_predictions", "missed_hands")}
    print(json.dumps(result, indent=2))


def quality_command(a):
    run, video = Path(a.run), Path(a.video)
    out = Path(a.out) if a.out else run/"quality"
    result = assess(run, video)
    summary = write_quality(run, video, out, result=result)
    if a.labels:
        ev = evaluate(run, Path(a.labels), allow_provisional=a.allow_provisional, split=a.split)
        q = evaluate_quality(result["windows"], Path(a.labels), ev, a.split)
        (out/f"quality_eval_{a.split or 'all'}.json").write_text(json.dumps(q, indent=2)+"\n")
        summary = {**summary, "label_evaluation": q}
    print(json.dumps(summary, indent=2))


def validate_command(a):
    result = validate_jsonl(Path(a.run)/a.file)
    print(json.dumps(result, indent=2))
    if not result["valid"]:
        sys.exit(2)


def conditions_init(a):
    out = Path(a.out)
    if out.exists():
        raise ValueError("File exists; choose a new filename (never overwritten)")
    out.write_text(json.dumps(conditions_template(sha256(Path(a.video))), indent=2)+"\n")
    print(out)


def governance_init(a):
    out = Path(a.out)
    if out.exists():
        raise ValueError("File exists; choose a new filename (never overwritten)")
    out.write_text(json.dumps(governance_template(), indent=2)+"\n")
    print(out)


def fetch_command(a):
    report = fetch_model(Path(a.model))
    if a.rtm:
        from .hybrid import fetch_rtm_models
        report = {"mediapipe": report,
                  "rtm": fetch_rtm_models(Path(a.rtm_models), Path(a.rtm_zips) if a.rtm_zips else None)}
    print(json.dumps(report, indent=2))


def build_parser() -> argparse.ArgumentParser:
    """The single source of truth for command options (also used by the Django job worker)."""
    parser = argparse.ArgumentParser(description="EgoHand Twin: offline 3D hand landmark reconstruction")
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("doctor", help="Inspect this machine and installed dependencies")
    p.set_defaults(func=doctor)
    p = commands.add_parser("fetch-model", help="Download the versioned official MediaPipe task model")
    p.add_argument("--model", default="models/hand_landmarker.task")
    p.add_argument("--rtm", action="store_true",
                   help="Also download the RTMDet/RTMPose hand models (Apache-2.0) for --preset hybrid")
    p.add_argument("--rtm-models", default="models/rtm")
    p.add_argument("--rtm-zips", help="Folder that already holds the two OpenMMLab zips (no download)")
    p.set_defaults(func=fetch_command)
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
    p.add_argument("--rescue-crop", action="store_true", default=None, help="Historical center-crop rescue on the downscaled frame (wrist dedupe)")
    p.add_argument("--rescue", help="Experimental full-resolution crop strategies, comma-separated: guided,center,tiles")
    p.add_argument("--max-crops", type=int, default=4, help="Maximum crop proposals evaluated per frame")
    p.add_argument("--crop-max-side", type=int, help="Area-downscale each rescue crop to at most this many pixels")
    p.add_argument("--dedupe", choices=["landmarks", "wrist"], default="landmarks",
                   help="Duplicate rule for --rescue candidates")
    p.add_argument("--governance", help="governance.json (purpose, consent, retention, redaction, lens source); "
                                        "validated before processing, copied into manifest.json")
    p.add_argument("--timestamp-source", choices=["auto", "frames"], default="auto",
                   help="auto: verified packet PTS (fast); frames: decode every frame with FFprobe")
    p.add_argument("--no-smoothing", action="store_true")
    p.add_argument("--tracker-units", choices=["normalized", "diagonal"], default="normalized",
                   help="Association distance units; diagonal is aspect-ratio correct")
    p.add_argument("--box-link", action="store_true", default=None,
                   help="Second tracker pass: link a detection to a just-missed track when their hand boxes "
                        "overlap >50%% (one identity, no predicted ghost over an observed hand)")
    p.add_argument("--predict-seconds", type=float, default=.15)
    p.add_argument("--retain-seconds", type=float, default=.8)
    p.add_argument("--preset", choices=sorted(PRESETS), default="baseline",
                   help="baseline: MediaPipe defaults (historical B0). recall: thresholds 0.3 + centre-crop rescue, "
                        "chosen on dev labels and confirmed once on holdout (provisional labels). accurate: recall + a reverse-time "
                        "pass (about 2x detector time). hybrid: recall + an RTMDet hand detector (needs fetch-model --rtm). "
                        "Explicit flags override.")
    p.add_argument("--hand-detector", action="store_true", default=None,
                   help="Add an RTMDet hand detector for hands MediaPipe misses (part of --preset hybrid; "
                        "needs: egohand fetch-model --rtm)")
    p.add_argument("--rtm-models", default="models/rtm", help="Folder with the RTM hand models")
    p.add_argument("--bidirectional", action="store_true", default=None,
                   help="Also run detection backwards in time and add hands the forward pass missed "
                        "(offline; about 2x detector time; part of --preset accurate)")
    p.add_argument("--detection-threshold", type=float)
    p.add_argument("--presence-threshold", type=float)
    p.add_argument("--tracking-threshold", type=float)
    p.add_argument("--no-video", action="store_true")
    p.add_argument("--rrd", action="store_true", help="Write synchronized Rerun recording")
    p.add_argument("--workers", type=int, default=1,
                   help="Detection processes (parallel chunked detection; 1 = sequential)")
    p.set_defaults(func=lambda a: process_parallel(a, workers=a.workers))
    p = commands.add_parser("replay", help="Rebuild Rerun replay from cached landmarks without inference")
    p.add_argument("video")
    p.add_argument("run")
    p.add_argument("--out", required=True, help="New .rrd output filename")
    p.add_argument("--lift", help="Optional lift_*.npz from 'egohand lift' for an experimental camera-space view")
    p.add_argument("--quality", help="Optional quality directory from 'egohand quality' for the review timeline")
    p.add_argument("--steps", help="Optional steps.json sidecar (human-authored step markers)")
    p.set_defaults(func=lambda a: rebuild_replay(Path(a.video), Path(a.run), Path(a.out),
                                                 Path(a.lift) if a.lift else None,
                                                 Path(a.quality) if a.quality else None,
                                                 Path(a.steps) if a.steps else None))
    p = commands.add_parser("evaluate", help="Score observed detections against manual labels")
    p.add_argument("run")
    p.add_argument("labels")
    p.add_argument("--wrist-threshold", type=float, default=.1)
    p.add_argument("--pck-threshold", type=float, default=.03)
    p.add_argument("--allow-provisional", action="store_true",
                   help="Score unreviewed v2 labels; results are stamped provisional")
    p.add_argument("--summary", action="store_true", help="Omit per-frame miss/false-positive lists")
    p.add_argument("--split", help="Only score frames from this label split (e.g. dev or holdout)")
    p.add_argument("--conditions", help="conditions.json: exclude flagged frames (reported) and slice recall by condition")
    p.set_defaults(func=evaluate_command)
    p = commands.add_parser("identity", help="Offline whole-track left/right vote -> RUN/identity.json")
    p.add_argument("run")
    p.add_argument("--margin", type=float, default=.15)
    p.add_argument("--min-observed", type=int, default=3)
    p.add_argument("--write-jsonl", action="store_true",
                   help="Also write landmarks.identity.jsonl with anatomical_side from the vote (assumes wearer hands)")
    p.set_defaults(func=identity_command)
    p = commands.add_parser("lift", help="EXPERIMENTAL camera-space PnP under an assumed fisheye lens")
    p.add_argument("run")
    p.add_argument("--hfov", type=float, nargs="+", default=[150.],
                   help="Assumed horizontal field(s) of view in degrees; several values give a sensitivity sweep")
    p.add_argument("--max-reproj-px", type=float, default=25.)
    p.set_defaults(func=lift_command)
    p = commands.add_parser("quality", help="Task-specific quality signals and a timestamped review queue (cached run)")
    p.add_argument("run")
    p.add_argument("video")
    p.add_argument("--out", help="Output directory (default RUN/quality)")
    p.add_argument("--labels", help="Optional labels to evaluate the flags against")
    p.add_argument("--allow-provisional", action="store_true")
    p.add_argument("--split")
    p.set_defaults(func=quality_command)
    p = commands.add_parser("export-segments", help="Copy cached records for queue intervals of one status")
    p.add_argument("run")
    p.add_argument("--out", required=True)
    p.add_argument("--status", choices=["suitable", "needs_review", "insufficient_evidence"], default="suitable")
    p.set_defaults(func=lambda a: print(json.dumps(export_segments(Path(a.run), Path(a.out), a.status), indent=2)))
    p = commands.add_parser("compare", help="Same-moment image: flat frame + 2D overlay vs 3D hand from three views")
    p.add_argument("video")
    p.add_argument("run")
    p.add_argument("--out", required=True, help="New .png path (private: contains footage)")
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--frame", type=int)
    group.add_argument("--time", type=float, help="Seconds on the run time base (nearest processed frame)")
    p.set_defaults(func=lambda a: print(json.dumps(compare(Path(a.video), Path(a.run), Path(a.out),
                                                           a.frame, a.time), indent=2)))
    p = commands.add_parser("steps-init", help="Write an empty steps.json sidecar bound to a run")
    p.add_argument("run")
    p.add_argument("--out", required=True)
    p.set_defaults(func=lambda a: print(write_template(Path(a.run), Path(a.out))))
    p = commands.add_parser("steps-check", help="Validate a steps.json sidecar against its run")
    p.add_argument("run")
    p.add_argument("steps")
    p.set_defaults(func=lambda a: print(json.dumps(load_steps(Path(a.steps), Path(a.run)), indent=2)))
    p = commands.add_parser("validate", help="Validate a run's per-frame JSONL against egohand_twin_frame.schema.json")
    p.add_argument("run")
    p.add_argument("--file", default="landmarks.jsonl", help="JSONL file inside the run (e.g. landmarks.identity.jsonl)")
    p.set_defaults(func=validate_command)
    p = commands.add_parser("conditions-init", help="Write an empty conditions.json bound to a source video")
    p.add_argument("video")
    p.add_argument("--out", required=True)
    p.set_defaults(func=conditions_init)
    p = commands.add_parser("conditions-apply",
                            help="Write <file>.conditions.jsonl with frame conditions/exclusions (input unchanged)")
    p.add_argument("run")
    p.add_argument("conditions")
    p.add_argument("--file", default="landmarks.jsonl")
    p.set_defaults(func=lambda a: print(apply_conditions(Path(a.run), Path(a.conditions), a.file)))
    p = commands.add_parser("label-review", help="Sheets with provisional labels drawn + review.csv for a human reviewer")
    p.add_argument("video")
    p.add_argument("labels")
    p.add_argument("--out", required=True)
    p.set_defaults(func=lambda a: print(json.dumps(label_review_pack(Path(a.video), Path(a.labels), Path(a.out)))))
    p = commands.add_parser("label-review-apply", help="Merge a filled review.csv into a new labels file")
    p.add_argument("labels")
    p.add_argument("review_csv")
    p.add_argument("--reviewer", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(func=lambda a: print(json.dumps(apply_label_review(
        Path(a.labels), Path(a.review_csv), a.reviewer, Path(a.out)), indent=2)))
    p = commands.add_parser("governance-init", help="Write a governance.json template to fill in")
    p.add_argument("--out", required=True)
    p.set_defaults(func=governance_init)
    p = commands.add_parser("retention-report", help="List runs and their retention status (never deletes)")
    p.add_argument("root", nargs="?", default="runs")
    p.add_argument("--today", help="ISO date to evaluate against (default: today)")
    p.set_defaults(func=lambda a: print(json.dumps(retention_report(
        Path(a.root), date.fromisoformat(a.today) if a.today else date.today()), indent=2)))
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
    return parser


def process_args(argv: list[str]) -> argparse.Namespace:
    """Parse and resolve 'process' options exactly as the command line does.

    Raises ValueError (never SystemExit) so a long-running job worker survives bad options.
    """
    try:
        args = build_parser().parse_args(["process", *argv])
    except SystemExit as exit_:
        raise ValueError(f"invalid process options: {' '.join(argv)}") from exit_
    apply_preset(args)
    for name in ["max_width", "stride", "max_frames", "duration", "num_hands", "workers", "max_crops", "crop_max_side"]:
        value = getattr(args, name, None)
        if value is not None and value <= 0:
            raise ValueError(f"{name.replace('_', '-')} must be positive")
    if args.start_seconds < 0:
        raise ValueError("start-seconds must be nonnegative")
    for name in ["detection_threshold", "presence_threshold", "tracking_threshold"]:
        if not 0 <= getattr(args, name) <= 1:
            raise ValueError(f"{name} must be between 0 and 1")
    return args


def main():
    parser = build_parser()
    args = parser.parse_args()
    if getattr(args, "command", None) == "process":
        apply_preset(args)
    for name in ["max_width", "stride", "max_frames", "duration", "num_hands", "samples", "step_frames", "workers", "max_crops", "crop_max_side", "wrist_threshold", "pck_threshold"]:
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
