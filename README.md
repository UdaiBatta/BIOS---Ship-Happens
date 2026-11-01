# EgoHand Twin — BIOS Ship Happens (PS4: 3D hand motion)

EgoHand Twin reconstructs hand motion from head-mounted factory video, offline on a CPU, and helps a data team find which seconds are **usable, uncertain or missing**. Every number traces back to source frames.

```text
video -> 21 image + 21 hand-relative 3D landmarks per hand -> short-term tracks with explicit states
      -> task-specific quality windows -> ranked review queue -> traceable exports + synchronized replay
```

Two users: a data engineer preparing hand-motion data, and expert knowledge capture (replay an expert's hands, mark steps, compare flat video with 3D). EgoHand Twin complements setup sheets, ERP and cross-training; it does not replace them.

## Results at a glance

Common clips: the first 30 seconds of every locally supplied clip are the agreed comparison interval. Coverage and stability are reported separately from accuracy in [COMMON_CLIPS_RESULTS](docs/COMMON_CLIPS_RESULTS.md) when processing completes.

| Preset | Common-clip recall | Precision | F1 | Wrong-side rate |
| --- | --- | --- | --- | --- |
| baseline | Not measured | Not measured | Not measured | Not measured |
| recall | Not measured | Not measured | Not measured | Not measured |
| accurate | Not measured | Not measured | Not measured | Not measured |
| hybrid | Not measured | Not measured | Not measured | Not measured |

These accuracy cells require human labels and denominators. Unreviewed labels remain provisional. Current laptop speed verification is in progress; the review-time pilot is not measured. Depth remains an assumed-lens estimate, the surface is generated from joints, and camera motion is not compensated. See [submission status](docs/FINAL_SUBMISSION_STATUS.md) and [performance](docs/PERFORMANCE_REPORT.md).

## Current status (1 Nov 2026)

Verification in this session: **197 pipeline tests passed, 1 skipped; 42 of 42 backend tests passed**. Browser verification and its limits are recorded in [BUG_BASH](docs/BUG_BASH.md).

The current session's common accuracy has **not been measured**. The local `labels_v2` inputs needed to rescore earlier results are missing. [RESULTS_V2](docs/RESULTS_V2.md) and the other linked experiment reports retain historical, provisional measurements from one clip; those figures are not current-session results.

| Capability | Current status |
| --- | --- |
| MediaPipe landmarks, short-term tracking, explicit observed/predicted/lost states, raw and filtered exports | Implemented; predicted landmarks are 2D only |
| Offline smoothing | Implemented: RTS-smoothed wrists and One Euro-smoothed finger offsets |
| Local review viewer | Hand posture is the default 3D view. Experimental camera space has a labeled posture fallback when depth is unavailable. Viewpoints, follow-hand camera, state timeline, frame inspection, event review and exports are available. |
| Generated 3D hand surface | Implemented for backend runs with camera-space landmarks; 970 vertices and 1,872 triangles. Bone-length calibration is applied. This is a generated visualization, not MANO/WiLoR fitting or validated geometry. |
| Motion events | Inferred candidates with evidence links and review state; thresholds are heuristic and unvalidated |
| Privacy scan | Experimental face-only review flags; not a privacy check or certification |
| Camera-space lift | Experimental and based on assumed lens parameters; depth is unvalidated |
| Current-session accuracy and user benefit | Not measured |
| Fitted MANO/WiLoR hand model and robot export | Not implemented |

Older performance and accuracy tables remain in the linked historical reports with their original caveats. See [KNOWN_LIMITATIONS](docs/KNOWN_LIMITATIONS.md) and [TODO](docs/TODO.md) for current measurement gaps.

## Quick start

**One command (viewer + backend + worker):** put your videos in `media/` at the repo root (git-ignored, never committed), then run

```sh
bash scripts/run_local.sh                                          # macOS / Linux
powershell -ExecutionPolicy Bypass -File scripts\run_local.ps1     # Windows (add -Test to run all tests first)
```

It installs dependencies, registers every video in `media/` (and the handoff clip in `data/private/` if present), starts the worker and opens http://127.0.0.1:8000/. Selecting a video on the **Backend** row loads its newest completed run, or a preview when no run exists. Click **Process** for a new run.

### Manual setup

Requirements: Python 3.11 or 3.12, FFmpeg/FFprobe, a laptop CPU.
- **Linux:** MediaPipe also needs `libgles2 libegl1`.
- **macOS:** `brew install ffmpeg`.
- **Windows:** put FFmpeg on PATH, or set `EGOHAND_FFMPEG_DIR` to its `bin` folder. The CLI, backend and launch scripts use this folder before PATH. In PowerShell: `$env:EGOHAND_FFMPEG_DIR = 'C:\path\to\ffmpeg\bin'`.

```sh
uv sync --extra dev --extra viewer
uv run egohand doctor                 # checks packages and that MediaPipe's native library loads
uv run egohand fetch-model
uv run rerun analytics disable        # keep the viewer fully offline
```

Process a clip with the chosen detector and review it (authorized clips go in `data/private/`, which git ignores):

```sh
V=data/private/clip.mp4
uv run egohand process $V --out runs/clip --duration 30 --preset recall --rrd --governance data/private/governance.json
uv run egohand validate runs/clip                       # per-frame JSON Schema check
uv run egohand quality runs/clip $V                     # -> runs/clip/quality/ (windows, queue, summary)
uv run egohand replay $V runs/clip --out runs/clip/review.rrd --quality runs/clip/quality
uv run rerun runs/clip/review.rrd
```

- `--preset baseline` (the default) reproduces the historical plain-MediaPipe runs. Explicit `--detection-threshold` or `--rescue` flags override a preset.
- Without `--governance`, the manifest records governance as `not_recorded`.
- If the native viewer fails, serve it to this computer only and open `http://127.0.0.1:9091/?url=rerun%2Bhttp%3A%2F%2F127.0.0.1%3A9877%2Fproxy`:

  ```sh
  uv run rerun --serve-web --bind 127.0.0.1 --port 9877 --web-viewer-port 9091 runs/clip/review.rrd
  ```

## Backend API (for the frontend)

A Django service in `backend/` exposes runs, frames, track lanes, quality windows, the review queue (with reviewer decisions), a frame-exact H.264 proxy and exports as a JSON API. A database-backed worker processes jobs. See [docs/BACKEND_API.md](docs/BACKEND_API.md).

```sh
uv sync --extra dev --extra viewer --extra backend
cd backend && uv run python manage.py migrate
uv run python manage.py runserver 127.0.0.1:8000       # and, in another terminal:
uv run python manage.py egohand_worker --recover
```

Open **http://127.0.0.1:8000/**: the teammate's viewer is served with a *Backend* toolbar for loading completed runs (landmarks, side votes, experimental lift, frame-exact proxy video) or queueing new ones.

## Workflow commands

| Goal | Command |
| --- | --- |
| Export only usable intervals | `egohand export-segments RUN --out DIR --status suitable` |
| Same-moment flat video vs 3D | `egohand compare VIDEO RUN --time 6.0 --out RUN/why3d.png` |
| Teach-back step markers | `egohand steps-init RUN --out RUN/steps.json`, `steps-check`, then `replay ... --steps RUN/steps.json` |
| Offline left/right vote | `egohand identity RUN --write-jsonl` (assumes every hand belongs to the wearer) |
| Capture conditions and exclusions | `egohand conditions-init VIDEO --out c.json`; `evaluate ... --conditions c.json`; `conditions-apply RUN c.json` |
| Governance and retention | `egohand governance-init --out g.json`; `egohand retention-report runs` (lists only, never deletes) |
| Labels and evaluation | `egohand annotation-set` → label → `egohand label-review` (human check) → `label-review-apply` → `egohand evaluate RUN LABELS --split dev\|holdout` |
| Experimental camera space | `egohand lift RUN --hfov 120 150 180`; `replay ... --lift RUN/lift_hfov150.npz` |

Run `uv run egohand <command> --help` for options. Further experimental flags:
- `--rescue guided,center,tiles` with `--max-crops` and `--crop-max-side`;
- `--tracker-units diagonal`;
- `--timestamp-source frames` (the slow full-decode probe).

## Outputs

| File | Content |
| --- | --- |
| `landmarks.jsonl` | One object per processed frame, including empty frames; raw and filtered coordinates, states, `missing_reason`, provenance, frame quality. Validates against `src/egohand_twin/schemas/egohand_twin_frame.schema.json`. |
| `landmarks.csv` / `landmarks.npz` | One row per landmark / one row per track sample (21×3, NaN when missing; load with `allow_pickle=False`) |
| `manifest.json` | Source and model hashes, all parameters (including the preset), coordinate definitions, governance, capture/lens provenance, package versions |
| `metrics.json` | Coverage, per-stage timing, detector latency, sampled memory. **Coverage is not recall.** |
| `tracking_events.csv` | Timestamped state changes with `missing_reason` |
| `preview.mp4` / `replay.rrd` | 1600×900 side-by-side render (header states the settings) / Rerun recording |
| `quality/` | `quality_frames.csv`, `quality_windows.json`, `review_queue.csv/json`, `quality_summary.json` |
| `identity.json`, `*.identity.jsonl`, `*.conditions.jsonl`, `lift_*`, `steps.json`, `why3d*.png` | Optional derived files; inputs are never modified and outputs never overwritten |

Identity votes are bound to the exact `landmarks.jsonl` bytes by `landmarks_sha256`; the viewer and evaluator reject foreign or older unbound identity files. To regenerate an older file, preserve it under a backup name first. The identity command preflights both outputs when `--write-jsonl` is requested, and lift sweeps preflight every JSON/NPZ pair before writing any of them.

## Data contract (summary; full definitions in [DEFINITIONS](docs/DEFINITIONS.md))

- **Raw and filtered values are kept separately.** `image_xyz_raw` and `world_xyz_m_raw` are model outputs; `image_xyz` and `world_xyz_m` are One Euro filtered.
- **Image coordinates:** `image_*` x/y are normalized to the source frame. z is wrist-relative model depth, **not metric**.
- **Hand-relative 3D:** `world_*` is MediaPipe's hand-relative estimate in metres, origin near the hand centre. It is **not** camera, world or factory coordinates. Display spacing between hands is arbitrary.
- **Missing data:** `predicted` carries extrapolated 2D only, `lost` and `retired` carry no coordinates, and none of these count as detections. `missing_reason` is an inferred hint (`out_of_view` or `unknown`).
- **Scores that are not quality measures:** `handedness_score` and `p_R` are left/right classifier probabilities, **not** landmark or detection quality. `confidence` is null because no calibrated confidence exists.
- **Identity:** track IDs are short-term associations; `anatomical_side` is `unknown` unless the offline vote file is used.
- **Camera-space fields are not emitted:** `cam_xyz_m`, wrist pose and grip aperture need a calibrated lens.

## Evaluation

The full method is in [DEFINITIONS](docs/DEFINITIONS.md), with results in [RESULTS_V2](docs/RESULTS_V2.md).
- Labels are split-aware (dev / holdout).
- Matching uses observed raw wrists only, one-to-one, gated at 0.10 image diagonals.
- Unreviewed labels need `--allow-provisional`, and every result from them is stamped provisional.
- Reports cover: recall and precision with Wilson intervals; recall by visibility, side, tag and condition; left/right confusion; ID changes; fragments; continuity; wrist-gate audit; `missing_reason` checks.

## Privacy

- **Kept out of git:** footage, labels, runs, recordings, previews and NPZ files stay in ignored local folders. The fresh remote-history scan passed on 1 Nov; the local all-ref scan flagged checkpoint artifacts. Release attachments and historical internal text still block publication. See [PUBLICATION_AUDIT](docs/PUBLICATION_AUDIT.md).
- **Repository access:** keep this repository private while the restricted release assets are attached ([REFERENCE_ARTIFACTS](docs/REFERENCE_ARTIFACTS.md)). A public copy must be source-only, and docs that describe the footage must be removed first.
- **Viewer:** disable Rerun analytics.
- **Governance fields:** these record operator statements, which the software does not verify.

## Frontend viewer (teammate's prototype)

`frontend/prototype/index.html` is a single-file offline viewer: video with the 2D skeleton, 3D hands, reliability lanes, signals, events and exports. It opens with clearly badged synthetic data and can load a local `landmarks.jsonl`, `identity.json`, `lift_*` files and a video; nothing is uploaded. See [frontend/README.md](frontend/README.md).

`schema/egohand_twin_frame.schema.json` is the per-frame JSON Schema (identical to the copy packaged in `src/egohand_twin/schemas/` and used by `egohand validate`). `schema/egohand_twin_frame.example.json` is a synthetic example.

## Compliance setup (every teammate, right after cloning)

```sh
git config core.hooksPath .githooks
```

This turns on the pre-commit hook. It rejects:
- images or video outside `docs/synthetic/`;
- arrays, caches and model files (`.npy`, `.pkl`, `.jsonl`, `.pth`, `.task`, ...);
- anything in `data/`, `outputs/`, `frames/` or `labels/`;
- any file over 2 MB.

Before making the repository public, run `scripts/check_history.sh` to scan the full history for media, data or model files.

## Documentation

| Document | Use |
| --- | --- |
| [PRODUCT_BRIEF](docs/PRODUCT_BRIEF.md) | Product, status audit, priorities, organizer questions |
| [RESULTS_V2](docs/RESULTS_V2.md) | All current measurements with denominators and reproduction commands |
| [DEMO_AND_QA](docs/DEMO_AND_QA.md) | Five-minute demo, slides, claims checklist, judges' Q&A, user-test protocols |
| [DEFINITIONS](docs/DEFINITIONS.md) | Frozen definitions of labels, states and metrics |
| [SUBMISSION](docs/SUBMISSION.md) | Submission text and checklist |
| [DEMO_SCRIPT](docs/DEMO_SCRIPT.md) | Current local viewer demo path and supported claims |
| [TODO](docs/TODO.md) | Deferred work with blockers |
| [BUILD_PROMPT](docs/BUILD_PROMPT.md) | Prompt for future feature work |
| [MILESTONE_REPORT](docs/MILESTONE_REPORT.md), [WILOR_FEASIBILITY](docs/WILOR_FEASIBILITY.md), [AGENT_CONTINUATION_PROMPT](docs/AGENT_CONTINUATION_PROMPT.md), [REFERENCE_ARTIFACTS](docs/REFERENCE_ARTIFACTS.md) | Historical baseline and handoff material |

## Repository structure

```text
src/egohand_twin/
  cli.py         commands and presets          pipeline.py   timestamped processing, exports, timing
  model.py       MediaPipe wrapper, crops      tracking.py   association, states, smoothing, missing_reason
  render.py      preview video, Rerun replay   evaluation.py labels vs runs, continuity
  annotate.py    annotation sets, label review quality.py    quality windows, review queue, segment export
  identity.py    offline left/right vote       compare.py    same-moment flat vs 3D image
  steps.py       steps.json sidecar            conditions.py capture conditions and exclusions
  governance.py  governance, retention         schema.py     JSON Schema validation (+ schemas/)
  lift.py        EXPERIMENTAL camera-space PnP parallel.py   parallel chunked detection, seam repair
backend/         Django API (api/: models, views, services, jobs, worker command, tests)
tests/           core and backend test suites
```

## References

- [MediaPipe Hand Landmarker (Python)](https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker/python)
- [Rerun timelines](https://rerun.io/docs/concepts/logging-and-ingestion/timelines)
- [OpenCV PnP](https://docs.opencv.org/4.x/d5/d1f/calib3d_solvePnP.html) and [fisheye model](https://docs.opencv.org/4.x/db/d58/group__calib3d__fisheye.html)
- [WiLoR](https://github.com/rolpotamias/WiLoR) (mesh feasibility only; not integrated)
