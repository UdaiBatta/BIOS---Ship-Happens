# EgoHand Twin — BIOS Ship Happens (PS4: 3D hand motion)

EgoHand Twin reconstructs hand motion from head-mounted factory video, offline on a CPU, and helps a data team find which seconds are **usable, uncertain or missing**. Every number traces back to source frames.

```text
video -> 21 image + 21 hand-relative 3D landmarks per hand -> short-term tracks with explicit states
      -> task-specific quality windows -> ranked review queue -> traceable exports + synchronized replay
```

Two users: a data engineer preparing hand-motion data, and expert knowledge capture (replay an expert's hands, mark steps, compare flat video with 3D). EgoHand Twin complements setup sheets, ERP and cross-training; it does not replace them.

## Status (31 Oct 2026)

Measured on one clip (one of four recording families) with **provisional labels**. A single annotator in the coding session made the labels and no person has reviewed them yet; see [RESULTS_V2](docs/RESULTS_V2.md).

| Capability | Status |
| --- | --- |
| Landmarks, tracking (observed / predicted 2D-only / lost / retired), raw + filtered exports, Rerun replay | Implemented, verified on real footage |
| Detection recovery, `--preset recall` (thresholds 0.3 + centre-crop rescue) | Holdout visible-hand recall 19/78 → 39/78, precision 39/40; more track fragmentation (2.17 vs 1.60 IDs per hand) |
| `--preset accurate` (recall + a reverse-time detection pass) | Holdout recall 39/78 → 46/78, precision 46/48; dev 36/72 → 41/72 with no false positives; about 2× detector time; no gain on hands cut off at the bottom edge |
| Quality windows, review queue, segment export, Rerun quality timeline | Implemented; heuristic. Flags catch 22/35 missed-hand frames on holdout; about 12 review items per minute |
| Reliability in replay: state lanes, side probability, `missing_reason`, units | Implemented; `out_of_view` contradicted in 6/15 holdout cases, so treat it as a hint |
| Same-moment flat-vs-3D image, `steps.json` step markers with sign-off | Implemented; whether 3D helps users is **not measured** |
| Per-frame JSON Schema validation, governance and lens provenance in the manifest | Implemented (manifest schema 0.5) |
| Faster processing | 30 s clip end-to-end 129 s → 57 s (verified packet timestamps). Parallel chunked detection (`--workers 2`): 63 s → 50 s for the recall preset, identical detections |
| Django backend API with job worker | Implemented; 9 backend tests; endpoints answer in 5–32 ms once a run is indexed |
| Camera-space PnP lift (`egohand lift`) | **Experimental**: assumed lens; depth moves ±25% with the assumed FOV |
| Solid 3D hands in the viewer | Low-poly surface (432 vertices) generated from the 21 lifted joints when a backend run loads: rounded fingers and a palm slab, typical thickness scaled to the measured palm. **Not a fitted hand-shape model** (no MANO/WiLoR); same assumed-lens depth caveats |
| Fitted meshes (MANO/WiLoR), robot export, bone calibration, privacy flags, action events, user tests | Not implemented — [TODO](docs/TODO.md) |

## Quick start

**One command (viewer + backend + worker):** put your videos in `media/` at the repo root (git-ignored, never committed), then run

```sh
bash scripts/run_local.sh                                          # macOS / Linux
powershell -ExecutionPolicy Bypass -File scripts\run_local.ps1     # Windows (add -Test to run all tests first)
```

It installs dependencies, registers every video in `media/` (and the handoff clip in `data/private/` if present), starts the worker and opens http://127.0.0.1:8000/. Pick a video on the **Backend** row and click **Process**.

### Manual setup

Requirements: Python 3.11 or 3.12, FFmpeg/FFprobe, a laptop CPU.
- **Linux:** MediaPipe also needs `libgles2 libegl1`.
- **macOS:** `brew install ffmpeg`.
- **Windows:** put FFmpeg on PATH.

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

- **Kept out of git:** footage, labels, runs, recordings, previews and NPZ files stay in `data/` and `runs/`, which are git-ignored. No commit on any branch contains media or data files (checked 31 Oct).
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
tests/           91 core tests; backend/api/tests: 9 API tests
```

## References

- [MediaPipe Hand Landmarker (Python)](https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker/python)
- [Rerun timelines](https://rerun.io/docs/concepts/logging-and-ingestion/timelines)
- [OpenCV PnP](https://docs.opencv.org/4.x/d5/d1f/calib3d_solvePnP.html) and [fisheye model](https://docs.opencv.org/4.x/db/d58/group__calib3d__fisheye.html)
- [WiLoR](https://github.com/rolpotamias/WiLoR) (mesh feasibility only; not integrated)
