# EgoHand Twin — BIOS Ship Happens

Offline reconstruction and inspection of hand posture from factory POV video. This first milestone implements MediaPipe's 21 image landmarks and 21 estimated hand-relative 3D landmarks, short-term identity tracking, explicit missing-data states, and synchronized replay. Meshes, calibrated camera poses, and absolute factory coordinates are not implemented.

See [the measured milestone report](docs/MILESTONE_REPORT.md) for the real-footage results and known detection failures.

**Hackathon category:** PS4 — 3D Hand Motion. **Current status:** functioning MediaPipe skeleton baseline, tested on a 30-second interval from one supplied factory clip. Mesh reconstruction and calibrated world-space tracking remain pending. The [submission guide](docs/SUBMISSION.md) contains a concise project summary, measured results and the remaining deliverables.

## Quick start

Requirements: Python 3.11 or 3.12, FFmpeg/FFprobe, ordinary laptop CPU. Python 3.14 is intentionally excluded. Setup with [uv](https://docs.astral.sh/uv/):

```sh
uv sync --extra dev --extra viewer
uv run egohand doctor
uv run egohand fetch-model
```

On macOS, install FFmpeg with `brew install ffmpeg`. On Windows, install FFmpeg and put both executables on PATH. Download authorized factory clips to `data/private/` locally.

```sh
uv run egohand process data/private/clip.mp4 --out runs/clip_first30 --duration 30 --rrd
uv run rerun runs/clip_first30/replay.rrd
```

Open `runs/clip_first30/preview.mp4` for a portable, muted, side-by-side video. Rerun offers pause, timeline scrubbing, and a rotatable 3D view synchronized with source presentation timestamps. A `COMPLETE` marker indicates a successful run. Failed output folders must be removed or replaced with a fresh `--out` name before retrying.

Replay cached estimates without inference, including after viewer-layout changes:

```sh
uv run egohand replay data/private/clip.mp4 runs/clip_first30 --out runs/clip_first30/review.rrd
```

If the native viewer has a display/renderer problem, use a browser with a server bound to this computer only:

```sh
uv run rerun --serve-web --bind 127.0.0.1 --port 9877 --web-viewer-port 9091 runs/clip_first30/replay.rrd
```

Open `http://127.0.0.1:9091/?url=rerun%2Bhttp%3A%2F%2F127.0.0.1%3A9877%2Fproxy` locally. Pause, then double-click the current time and replace it with e.g. `6s` to inspect a specific moment. Drag inside the 3D view to orbit. The server remains private to the local computer and can be stopped with Ctrl+C.

Run a plain baseline for comparison on the identical interval:

```sh
uv run egohand process data/private/clip.mp4 --out runs/clip_baseline --duration 30 --identity baseline --no-smoothing
```

`--identity baseline` uses the result index as an ID with **no continuity guarantee**; it retains MediaPipe's internal video tracking. `--detector-mode image` separately disables MediaPipe's video-mode optimization. Compare each factor explicitly. `--no-video` excludes preview encoding; compare runtime only with equal settings. `--stride 2` samples every other source frame, with timestamp-aware tracking. Use stride 1 for final identity evaluation.

`--rescue-crop` is an **experimental, opt-in** detector fallback. When fewer than the requested number of hands are found, an independent image-mode detector checks a fixed center/lower crop, maps its image coordinates back to the full frame, and suppresses candidates whose wrists are within 0.10 normalized image units of an existing detection. Local 3D axes remain unchanged because the crop does not rotate the image. The crop can improve visible detection coverage but can also add false positives or duplicate hands; it is not a proven accuracy improvement. Its origin is recorded as `center_crop_rescue` in JSONL. Compare it against the identical tracker settings without rescue.

## Outputs

| File | Content |
| --- | --- |
| `landmarks.jsonl` | One object per processed frame, including empty frames; all raw and filtered coordinates and track states |
| `landmarks.csv` | One row per landmark; missing tracks have landmark index -1 and empty coordinates |
| `landmarks.npz` | One row per track-state sample, 21×3 arrays; missing data is NaN; load with `allow_pickle=False` |
| `manifest.json` | Source/model hashes, parameters, coordinate definitions, package versions |
| `metrics.json` | Coverage, runtime, inference latency, sampled process memory; accuracy remains null without labels |
| `tracking_events.csv` | Timestamped state transitions for finding uncertain/recovered intervals |
| `preview.mp4` / `preview.jpg` | 1600×900 synchronized inspection render / first frame with the largest observed-hand count |
| `replay.rrd` | Optional Rerun recording with video, skeletons and reliability events |
| `COMPLETE` | Successful completion marker |

Timestamp zero is the first source presentation timestamp; a selected interval preserves its original relative time. FFprobe supplies source PTS, including variable frame rates. Portable MP4 output requires CFR input so timing remains accurate; VFR inputs can use `--no-video --rrd`. Convert VFR footage to CFR explicitly if a portable render is needed. Preview audio is omitted. No source footage is uploaded by the processing command.

## Coordinate and reliability contract

- `image_xyz_raw`: normalized x/y, with wrist-relative model depth z measured in approximately x-normalized units. It is **not metric depth**.
- `world_xyz_m_raw`: MediaPipe's estimated meter coordinates with an origin near each hand's geometric center. These are **not absolute factory/world positions**. They have not been calibrated or validated against 3D ground truth.
- `image_xyz` and `world_xyz_m`: One Euro filtered values, or raw values with `--no-smoothing`. Raw estimates remain available for evaluation. Smoothing may add latency and does not establish improved accuracy.
- Rendering subtracts the wrist independently from each hand. Hand spacing in the 3D display is arbitrary; inter-hand distance and wrist trajectories cannot be read as factory geometry.
- `handedness_score` is a left/right classifier score, **not landmark/detection quality**. MediaPipe's confidence thresholds control detection internally; per-joint confidence is not fabricated.
- Handedness follows the current official Tasks API convention on input pixels. Input mirroring affects labels; validate left/right against a known hand before the demo.

Tracker assignment combines wrist motion, normalized hand shape and a soft handedness penalty using Hungarian matching. Spatial gates reject implausibly distant matches. State transitions:

```text
observed -> predicted (<=0.15s missing, 2D only) -> lost -> retired (>0.8s)
     ^          |                                  |
     +------ reacquired <--------------------------+
```

Reacquisition is allowed only before retirement. Prediction never supplies observed or raw coordinates and never invents 3D articulation. Lost/retired coordinates are null. A returning hand after retirement gets a new ID. IDs are short-term associations; crossings, camera movement and occlusions can still cause switches. There is no biometric identity claim. Two simultaneous hands can have the same estimated handedness; the tracker does not force one of each.

## Quantitative evaluation

```sh
uv run egohand sample-labels data/private/clip.mp4 --out data/private/annotations --samples 12 --duration 30
```

Inspect the full-resolution frames and populate a copy of `labels.template.json`, setting `reviewed` to true after review. **The generated template is unlabeled and cannot be scored unchanged.** Include every visible, labelable hand in each evaluated frame. Example:

```json
{
  "source_sha256": "COPY_FROM_RUN_MANIFEST",
  "reviewed": true,
  "frames": [
    {"frame_index": 0, "hands": [
      {"identity": "worker_left", "wrist_xy": [0.31, 0.76]}
    ]}
  ]
}
```

Optional `landmarks_xy` contains 21 normalized `[x,y]` points or null for unlabeled joints. Use consistent anatomical identities across frames. Annotate before examining model predictions where possible. Sample blur, gloves, occlusion, crossing and re-entry; reserve an untouched holdout for final reporting.

```sh
uv run egohand evaluate runs/clip_baseline data/private/labels.json
uv run egohand evaluate runs/clip_first30 data/private/labels.json
uv run pytest -q
```

Detection matching uses raw observed wrists within 0.10 of the image diagonal (configurable). Precision/recall are only meaningful under that matching protocol. PCK@0.03 diagonal is reported on matched hands if joint labels exist; missing detections are reported separately. Sampled ID switches count changes in associated track ID for the same annotated identity between matched samples. Sparse labels miss events and do not give full-sequence ID-switch counts. No 3D error or industrial productivity result is claimed without appropriate ground truth/testing. Detection coverage is **not recall**.

## Privacy and submission

`data/`, `runs/`, `models/`, videos, Rerun recordings and NPZ exports are ignored. All derived outputs can reveal private task motion and must stay private along with source footage. Do not force-add them. This repository contains source, configuration, tests and documentation; use the designated private submission folder for processed clips and motion exports. Model assets are downloaded separately from the official source. Confirm repository access requirements with the organizers before submitting its link.

## Repository structure

```text
src/egohand_twin/
  cli.py          Commands, environment inspection and annotation sampling
  model.py        Official MediaPipe task wrapper and optional crop rescue
  tracking.py     Short-term identity assignment, state transitions and smoothing
  pipeline.py     Timestamped processing, exports and measured performance
  render.py       Video composition and synchronized Rerun replay
  evaluation.py   Explicit-label precision, recall and sampled ID-switch evaluation
tests/            Tracking, coordinate mapping and evaluation checks
docs/             Measured results, submission guide and remaining milestones
pyproject.toml    Package, command entry point and dependencies
uv.lock           Locked dependency versions
```

## References

- [MediaPipe Python Hand Landmarker](https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker/python): current Tasks API, output definitions, handedness and video tracking.
- [Official model and configuration guide](https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker/index): versioned float16 task bundle and configuration semantics.
- [Rerun timeline concepts](https://rerun.io/docs/concepts/logging-and-ingestion/timelines): synchronized inspection.
- [WiLoR official implementation](https://github.com/rolpotamias/WiLoR): optional mesh feasibility investigation, not integrated.

See `docs/NEXT_MILESTONES.md` for the remaining hackathon work and `docs/WILOR_FEASIBILITY.md` for the mesh decision.
