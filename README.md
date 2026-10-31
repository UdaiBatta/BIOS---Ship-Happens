# EgoHand Twin — BIOS Ship Happens

Offline reconstruction and inspection of hand posture from factory POV video. This first milestone implements MediaPipe's 21 image landmarks and 21 estimated hand-relative 3D landmarks, short-term identity tracking, explicit missing-data states, and synchronized replay. Meshes, calibrated camera poses, and absolute factory coordinates are not implemented.

**Product direction (31 Oct, revised):** reconstruct hand motion from factory POV footage and help data teams find useful, uncertain and problematic segments to review. See the [product brief and status audit](docs/PRODUCT_BRIEF.md), the [v2 measured results](docs/RESULTS_V2.md) and the [demo script and judges' Q&A](docs/DEMO_AND_QA.md). The [first milestone report](docs/MILESTONE_REPORT.md) is kept as the historical baseline.

| Capability | Status |
| --- | --- |
| 21 image + 21 hand-relative 3D landmarks, tracking with explicit states, raw vs filtered exports, synchronized replay | Implemented and verified on real footage |
| Detection recovery (`--rescue-crop` + 0.3 thresholds) | Implemented. Holdout recall 19/78 → 39/78, precision 39/40, on **provisional, not yet human-reviewed** labels from one clip |
| Quality windows, review queue, segment export, Rerun quality timeline | Implemented, heuristic; flag catch rate and false-alarm burden measured on provisional labels |
| Verified fast timestamp probe, per-stage timing | Implemented and verified |
| Camera-space PnP lift (`egohand lift`) | **Experimental**: assumed lens, depth unvalidated |
| Meshes, robot export, SLAM, privacy flags, semantic actions | Not implemented |

**Hackathon category:** PS4 — 3D Hand Motion. **Current status:** functioning MediaPipe skeleton baseline, tested on a 30-second interval from one supplied factory clip. Mesh reconstruction and calibrated world-space tracking remain pending. The [submission guide](docs/SUBMISSION.md) contains a concise project summary, measured results and the remaining deliverables.

**Continue development:** use the detailed [continuation prompt](docs/AGENT_CONTINUATION_PROMPT.md) together with the supplied 27-page research PDF. The [reference-artifact guide](docs/REFERENCE_ARTIFACTS.md) explains the private release containing the original downloaded video, all three processed benchmark demos, cached estimates, interactive recordings, annotation templates, checksums and the unchanged PDF. Repository access is required; only one of the 40 original clips has been downloaded or benchmarked.

## Quick start

Requirements: Python 3.11 or 3.12, FFmpeg/FFprobe, ordinary laptop CPU. Python 3.14 is intentionally excluded. Setup with [uv](https://docs.astral.sh/uv/):

```sh
uv sync --extra dev --extra viewer
uv run egohand doctor
uv run egohand fetch-model
```

On Linux, MediaPipe also needs the system GL/EGL libraries (Debian/Ubuntu: `sudo apt-get install libgles2 libegl1`). Disable Rerun's usage analytics once per machine with `uv run rerun analytics disable`. The web viewer otherwise tries to reach rerun.io for telemetry; no footage is involved, but offline use should not depend on it.

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

## Detection recovery, quality review and exports (v2)

```sh
V=data/private/clip.mp4
T="--detection-threshold .3 --presence-threshold .3 --tracking-threshold .3"
uv run egohand process $V --out runs/clip_v2 --duration 30 --rrd --rescue-crop $T   # chosen on dev labels
uv run egohand quality runs/clip_v2 $V                                            # -> runs/clip_v2/quality/
uv run egohand replay $V runs/clip_v2 --out runs/clip_v2/review.rrd --quality runs/clip_v2/quality
uv run egohand export-segments runs/clip_v2 --out runs/clip_v2_suitable --status suitable
```

Teach-back helpers for expert knowledge capture:

```sh
uv run egohand compare $V runs/clip_v2 --time 6.0 --out runs/clip_v2/why3d_6s.png   # same moment: flat frame vs 3D hand, 3 views
uv run egohand steps-init runs/clip_v2 --out runs/clip_v2/steps.json                 # empty sidecar bound to source + run
uv run egohand steps-check runs/clip_v2 runs/clip_v2/steps.json
uv run egohand replay $V runs/clip_v2 --out runs/clip_v2/teach.rrd --steps runs/clip_v2/steps.json --quality runs/clip_v2/quality
```

- `compare` refuses frames without an observed hand and names the nearest observed frames. Its 3D panel shows MediaPipe's hand-relative estimate; joints hidden in the image are model-inferred.
- `steps.json` holds `{start_s, end_s, label, version, note, reviewer, signed_off}` on the run's time base. It is validated against the source hash and run id, and `signed_off` requires a reviewer.
- Steps are human-authored markers, not detections. Do not put worker names or scores in them.

The default detector settings are unchanged, so historical runs reproduce. Further experimental options:
- `--rescue guided,center,tiles` with `--max-crops` and `--crop-max-side` for full-resolution crops.
- `--tracker-units diagonal`.
- `egohand identity RUN` for an offline whole-track side vote.
- `egohand lift RUN --hfov 120 150 180` for camera space under an assumed lens.

`--timestamp-source frames` restores the slow full-decode timestamp probe; the default uses packet PTS, verified against decoded frames, with automatic fallback.

`quality/` contains:
- `quality_frames.csv`: per-frame signals.
- `quality_windows.json`: 1 s windows labeled `suitable`, `needs_review` or `insufficient_evidence`, with reason codes and evidence.
- `review_queue.csv` / `.json`: ranked intervals of at most 5 s, with track IDs, reasons, suggested actions, source hash and run id.
- `quality_summary.json`: per-clip summary.

These are **heuristic, task-specific** assessments for hand-motion inspection. *Insufficient evidence* means no *observed* hand, not no hand. Nothing is deleted or hidden.

Labels for evaluation: `egohand annotation-set` creates split-aware frames, grid sheets and a v2 template (gt_id, wearer side, visibility, tags, provenance). `egohand evaluate ... --split dev|holdout` scores them. Unreviewed v2 labels need `--allow-provisional`, and their results are stamped provisional.

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
- `world_xyz_m_raw`: MediaPipe's estimated meter coordinates with an origin near each hand's geometric center. These are **not absolute factory/world positions**. They have not been calibrated or validated against 3D ground truth. On the test clip the raw bone lengths of a track vary (median coefficient of variation 0.15).
- `lift_hfov*.npz` (experimental, separate files): camera coordinates (x right, y down, z forward) from PnP under an **assumed** equidistant fisheye. Depth changes by ±25% across assumed FOVs of 120–180°, and reprojection error cannot tell them apart. Not factory coordinates and not validated.
- `image_xyz` and `world_xyz_m`: One Euro filtered values, or raw values with `--no-smoothing`. Raw estimates remain available for evaluation. Smoothing may add latency and does not establish improved accuracy.
- Rendering subtracts the wrist independently from each hand. Hand spacing in the 3D display is arbitrary; inter-hand distance and wrist trajectories cannot be read as factory geometry.
- `missing_reason` (schema 0.3, non-observed tracks only) is `out_of_view` or `unknown`, with `missing_reason_basis` and `missing_reason_provenance: "inferred"`.
  - `out_of_view` means the extrapolated wrist left the image, or the last observed landmarks touched the border.
  - Everything else is `unknown`: the tracker cannot tell occlusion, blur and low detector score apart, so it does not guess.
  - On holdout (provisional labels), 6 of 15 `out_of_view` claims were contradicted by a labeled but undetected hand near the last position. Treat the reason as a hint.
  - The field appears in JSONL, CSV, NPZ and `tracking_events.csv`.
- Replay shows reliability directly:
  - Each label reads `#id side p_R=… state (reason)`, where `p_R` is side probability, not landmark quality.
  - A "Track state lanes" plot has one row per track: observed-Left green, observed-Right orange, predicted (2D-only) grey, lost red.
  - View titles state units and coordinate frames.
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

`data/`, `runs/`, `models/`, videos, Rerun recordings and NPZ exports are ignored in ordinary source commits. All derived outputs can reveal private task motion and must stay private along with source footage. At the user's request, a restricted reference set is attached to a private repository release for authorized continuation; see [access and restoration](docs/REFERENCE_ARTIFACTS.md). Keep this repository private while those assets are attached. Use the designated private submission folder for the official processed-clip submission, and prepare a separate source-only repository if public access is required. Model assets are downloaded separately from the official source.

## Repository structure

```text
src/egohand_twin/
  cli.py          Commands, environment inspection and annotation sampling
  model.py        Official MediaPipe task wrapper and optional crop rescue
  tracking.py     Short-term identity assignment, state transitions and smoothing
  pipeline.py     Timestamped processing, exports and measured performance
  render.py       Video composition and synchronized Rerun replay
  evaluation.py   Explicit-label precision, recall and sampled ID-switch evaluation
  annotate.py     Split-aware annotation sets and v2 label template
  identity.py     Offline whole-track left/right vote (unknown allowed)
  quality.py      Quality signals, windows, review queue, segment export
  lift.py         EXPERIMENTAL camera-space PnP under an assumed lens
  compare.py      Same-moment flat video vs 3D views (teach-back / demo)
  steps.py        steps.json sidecar: human step markers with sign-off
tests/            Tracking, detection crops, evaluation, quality and lift checks
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
