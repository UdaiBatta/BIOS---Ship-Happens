# MOTIONIQ: viewer prototype

`prototype/index.html` is a single-page viewer. Open it directly for the offline preview, or use the local backend for video registration and processing.

> Every value in the default demo is **synthetic**. The page shows a "SYNTHETIC DATA · not measured" badge until you load a real file.

## What's on screen

| # | Panel | What it shows | Pattern borrowed from |
|---|---|---|---|
| 1 | Video + 2D skeleton | Source frame (or a placeholder) with each hand's 21 points. Observed hands are solid, predicted hands are dashed (2D only), and reacquired hands get a ring. Each label gives side, state and the detection path (full frame / tile / guided crop / hand detector) | Rerun MediaPipe example |
| 2 | 3D hands | Hand-relative 3D or approximate camera-space 3D, depending on loaded data. Drag to orbit, scroll to zoom, and use Reset view or double-click to restore the view. Predicted and lost hands have no 3D. Mesh display options are available for observed 3D joints, including hand-relative posture. | Rerun / HOT3D viewer |
| 3 | Timeline | Spans the loaded run's own time range (interval runs such as `--start-seconds 60` start at 60 s). Per-hand breakdown (tracked / predicted / not tracked), then reliability lanes: left hand, right hand, other people, low-blur mask, camera-lift acceptance mask and, when meshes are loaded, a mesh lane. Lanes without source data in the run are hidden. "Camera lift accepted" means an observed hand has camera-space joints accepted by `motioniq lift` (its `--max-reproj-px` limit is applied there; the viewer assumes no threshold). Hover for values; click to seek | HOT3D quality masks, Invisible AI cycle breakdown |
| 4 | Signals | Available signal charts are derived from loaded data; charts without source data are hidden. | LeRobot visualiser, Foxglove plots |
| 5 | Events | Lost, reacquired, predicted, blur, 3D-not-valid, implausible-depth and missing-mesh events. Click to jump. "Problems only" filter | Twelve Labs result list, Drishti Trace |
| — | Frame details | Table view of the current frame: state, detection path, depth, aperture, reprojection, bone-length CV, displayed-side support, where the side came from, confidence, provenance, mesh and mesh-vs-PnP depth gap. Rows with no source data in the loaded run are hidden | Accessibility / evidence |
| — | Export | Frames JSONL (schema v1), events CSV, **Aria-compatible CSV** (landmarks remapped to Aria order, palm centre added; wrist rotation, palm normal and confidence stay blank because they are not estimated). The `.rrd` replay comes from the pipeline | Project Aria MPS |

Header chips: coverage is computed from the loaded file and labelled as coverage, not accuracy. The 3D-mode chip states the active representation. Hand posture is the default; the camera-space option shows a labeled hand-relative posture fallback with meshes when a frame has no accepted camera joints. Loading a run preserves the selected mode. Fallback geometry has no camera depth. Mesh surfaces are generated from observed hand-relative joints as well as accepted camera joints; predicted and lost hands do not get meshes. There are no recall or FPS chips: those numbers are in the pipeline's evaluation and `metrics.json`.

## Using the local backend (recommended for real runs)

Start the Django backend (see `../docs/BACKEND_API.md`), then open **http://127.0.0.1:8000/**. The same page is served with a second toolbar row, *Backend*:

- **Load run:** for a completed run, loads `landmarks.jsonl` and the optional identity/lift files advertised by the backend. It supports non-default FOVs and runs with no lift. It uses the same loaders and checks as the file buttons below. The H.264 proxy contains the selected source frames; the viewer uses its persisted `proxy.time_offset_s`, which can differ from the requested start when it falls between frames. Older unverified proxies are hidden; queue a new run to regenerate them.
- **Process:** queues a run for a registered video (preset, start, length) on the local worker, shows its stage and progress, and loads it when complete.
- **Token:** if the backend requires a token, open `http://127.0.0.1:8000/?token=…` once; it is kept for the browser session only.

Opened as a file (`file://`), the page stays fully offline: `backend-connector.js` does nothing and makes no network requests.

## Using real outputs (stays on the laptop)

- **Load JSONL:** schema-v1 records (see `../schema/`), the pipeline's own `runs/<run>/landmarks.jsonl` from `motioniq process`, or `landmarks.identity.jsonl` from `motioniq identity --write-jsonl`. A missing or `"unknown"` `anatomical_side` is treated as unavailable: the tracker's `side` (`Right`/`Left`) is used and the frame-details table says `tracker (online)`. Sides from the identity file show `whole-track vote`. Invalid lines are skipped, and the page says how many. A predicted or lost hand that carries 3D breaks the schema rule, so the page shows it as 2D only and warns you.
- **Add results** (select several files at once, for the loaded run; **disabled in the synthetic demo**, so real and synthetic data are never mixed). Everything is checked before it is merged, and a file that does not belong to the loaded run is rejected with the reason:
  - `lift_<tag>.npz` + `lift_<tag>.json` from `motioniq lift`: camera-space joints for observed hands. The pair must have the same tag and FOV and the same row counts, and the joints must reproject onto the run's 2D landmarks with the summary's lens. The lens shown comes only from `lift_<tag>.json` (its `camera` block, including its calibration status); without it the badge says "lens not loaded" and no frustum is drawn. Loading another lift (for example a FOV sweep) replaces the previous one.
  - `identity.json` from `motioniq identity`: its `landmarks_sha256` must match the exact bytes of the loaded `landmarks.jsonl`. Missing or foreign checksums are rejected before any labels change. A decisive whole-track vote replaces unavailable sides; sides already set by the file are kept; an `unknown` vote keeps the tracker side. Identity-labeled JSONL already contains its side labels and needs no identity file.
  - Mesh files from the WiLoR / HaMeR step (format below). Rows for predicted or lost hands, failed rows and rows that match no loaded hand are skipped and counted.
- **Load video:** plays a local clip in sync, using `timestamp_s`. When paused, the skeleton snaps to the frame the video shows; frame stepping seeks to the middle of each frame. No hand overlay is drawn outside the run's time range. The file is never uploaded. With the synthetic demo the video badge says that the overlay is synthetic.
- Do not commit real outputs or screenshots of real footage. `*.jsonl` and media files are already git-ignored.

### Generated hand surfaces (backend runs)

Observed hand-relative or camera-space joints can generate a hand surface with `hand-mesh.js` (970 vertices and 1,872 triangles). Hand posture and camera-space fallback support Mesh and Mesh + skeleton; valid camera-space files retain their own meshes. Surfaces are built on demand with a bounded cache and per-track bone-length calibration, and are labelled as generated, not fitted. MANO/WiLoR/HaMeR fitting is unavailable.

### Mesh file format (what the mesh step should write)

Vertices must already be in **camera-frame metres** (x right, y down, z forward), placed by the pipeline (for example by re-running `lift.solve_hand` with the MANO joints). The viewer never places meshes itself.

- **NPZ** (`mesh_<backend>_*.npz`, read in the browser): `frame_index` (n), `track_id` (n), `vertices_cam_m` (n, V, 3; float16/32/64), `faces` (F, 3). Optional: `ok` (n, bool), `backend` (string, e.g. `"wilor"` or `"hamer"`), `depth_gap_m` (n) or `model_depth_m` + `pnp_depth_m` (n).
- **JSON**: `{ "backend": "wilor", "faces": [[i, j, k], ...], "meshes": [{ "frame_index", "track_id", "vertices_cam_m": [[x, y, z], ...], "ok"?, "depth_gap_m"? }] }`.
- **JSONL**: first line `{ "type": "mesh_header", "backend", "faces" }`, then one mesh record per line.

Closed meshes are drawn single-sided (winding detected per mesh from its signed volume, so mirrored left hands work); open surfaces are drawn double-sided. Mesh gaps shorter than 0.2 s stay visible in the mesh lane but are not listed as events. MANO faces and vertices derived from footage are private: keep them out of the repo.

Keys: `space` play/pause · `←/→` step one frame · `Home` jump to start. 3D view: drag to orbit, scroll to zoom, double-click or use Reset view to reset.

## Current local demo path

Start the local viewer, backend and worker using the repository's launch script. Select a registered video in the Backend row. If a completed run exists, the viewer loads the newest one; otherwise it previews the selected video. Click **Process** to queue a run explicitly. Review the synchronized video and landmarks, choose **Side / Top / Camera**, toggle **Follow hand**, and orbit/zoom/reset the 3D view. Inspect the timeline and frame details, and review heuristic events. Use **F** and **R** for failure/reacquisition event navigation. Set `MOTIONIQ_FFMPEG_DIR` to the FFmpeg `bin` folder when its tools are not on PATH.

## Visual rules

- Wearer-left is orange `#d95926`, wearer-right is blue `#3987e5`, and other people's hands are gray `#898781`. The two hand colours pass the colour-blind and contrast checks on the dark surface `#1a1a19`.
- Reliability is shown by line style and opacity, never by a new hue. Green/red are used only for true/false masks, always with ✓/✕ text.
- Text is always in ink colours. A small colour key carries hand identity.
- Honesty labels are always visible, for example "EXPERIMENTAL camera space · equidistant fisheye HFOV 150° · ASSUMED (not calibrated) · depth unvalidated", or "Hand-relative 3D estimates. Factory position and camera motion are not reconstructed."

## Next steps

1. Fitted MANO/WiLoR/HaMeR mesh inference is not integrated. The viewer's **Add results** input accepts externally produced mesh files in the format above.
2. Compare the viewer's lanes and event candidates against reviewed labels when evaluation inputs are available.
3. Camera-space estimates remain under an assumed lens until calibration inputs are verified and recorded in the manifest.

## Temporal consistency

Hand posture is wrist-centered with illustrative placement. The filtered 3D fingers use separate bone-length and timestamp-aware direction smoothing; raw exports remain unchanged. Side score is left/right classifier support, while landmark confidence is uncalibrated. See [POSE_STABILITY](../docs/POSE_STABILITY.md) for measured improvements and limits.
