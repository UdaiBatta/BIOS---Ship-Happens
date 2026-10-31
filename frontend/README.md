# EgoHand Twin: viewer prototype

`prototype/index.html` is a single offline page. Double-click it to open it in Chrome or Firefox. It needs no server, makes no network requests and uses no libraries.

> Every value in the default demo is **synthetic**. The page shows a "SYNTHETIC DATA · not measured" badge until you load a real file.

## What's on screen

| # | Panel | What it shows | Pattern borrowed from |
|---|---|---|---|
| 1 | Video + 2D skeleton | Source frame (or a placeholder) with each hand's 21 points. Observed hands are solid, predicted hands are dashed (2D only), and reacquired hands get a ring. Each label gives side, state and the detection path (full frame / tile / guided crop / hand detector) | Rerun MediaPipe example |
| 2 | 3D hands | **Ours:** both hands in camera space (metres) with the camera frustum (from the loaded lens model), the 0.2–0.9 m plausibility band, 2 s wrist trails and a two-finger gripper that follows the wrist and opens with the grip aperture. **Baseline:** MediaPipe hand-relative 3D at arbitrary spacing. **Skeleton / Mesh / Mesh + skeleton** switch for WiLoR/HaMeR meshes; a hand without a mesh keeps its skeleton. Hands that are predicted or lost never get 3D or a mesh | Rerun / HOT3D viewer, robot-export story |
| 3 | Timeline | Per-hand breakdown (tracked / predicted / not tracked), then reliability lanes: left hand, right hand, other people, low-blur mask, 3D-valid mask and, when meshes are loaded, a mesh lane (every / some / no observed hand has a mesh). Hover for values; click to seek | HOT3D quality masks, Invisible AI cycle breakdown |
| 4 | Signals | Reprojection error (px), grip aperture (m), wrist depth (m) and, when meshes carry it, the mesh-vs-PnP depth gap (cm). Each signal has its own axis, and the crosshair tooltip covers both hands | LeRobot visualiser, Foxglove plots |
| 5 | Events | Lost, reacquired, predicted, blur, 3D-not-valid, implausible-depth and missing-mesh events. Click to jump. "Problems only" filter | Twelve Labs result list, Drishti Trace |
| — | Frame details | Table view of the current frame: state, detection path, depth, aperture, reprojection, bone-length CV, P(right), where the side came from, confidence, provenance, mesh and mesh-vs-PnP depth gap | Accessibility / evidence |
| — | Export | Frames JSONL (schema v1), events CSV, **Aria-compatible CSV** (landmarks remapped to Aria order, palm centre added). LeRobot and `.rrd` exports come from the pipeline | Project Aria MPS, LeRobot |

Header chips: coverage is computed from the loaded file and labelled as coverage, not accuracy. Recall and FPS stay `[MEASURE]` until they are measured. The 3D-mode chip always states what the 3D is.

## Using real outputs (stays on the laptop)

- **Load JSONL:** either schema-v1 records (see `../schema/`) or the pipeline's own `runs/<run>/landmarks.jsonl` from `egohand process`. For pipeline records, the tracker's `side` (`Right`/`Left`) is mapped to wearer right/left; the frame-details table shows where each side came from. Invalid lines are skipped, and the page says how many. A predicted or lost hand that carries 3D breaks the schema rule, so the page shows it as 2D only and warns you.
- **Add results** (select several files at once, for the loaded run):
  - `lift_<tag>.npz` + `lift_<tag>.json` from `egohand lift`: camera-space joints for observed hands. The 3D badge, chip and frustum switch to the lift's assumed lens ("EXPERIMENTAL … depth unvalidated").
  - `identity.json` from `egohand identity`: whole-track left/right vote per track (`unknown` is kept).
  - Mesh files from the WiLoR / HaMeR step (format below). Rows for predicted or lost hands, failed rows and rows that match no loaded hand are skipped and counted.
- **Load video:** plays a local clip in sync, using `timestamp_s`. The file is never uploaded.
- Do not commit real outputs or screenshots of real footage. `*.jsonl` and media files are already git-ignored.

### Mesh file format (what the mesh step should write)

Vertices must already be in **camera-frame metres** (x right, y down, z forward), placed by the pipeline (for example by re-running `lift.solve_hand` with the MANO joints). The viewer never places meshes itself.

- **NPZ** (`mesh_<backend>_*.npz`, read in the browser): `frame_index` (n), `track_id` (n), `vertices_cam_m` (n, V, 3; float16/32/64), `faces` (F, 3). Optional: `ok` (n, bool), `backend` (string, e.g. `"wilor"` or `"hamer"`), `depth_gap_m` (n) or `model_depth_m` + `pnp_depth_m` (n).
- **JSON**: `{ "backend": "wilor", "faces": [[i, j, k], ...], "meshes": [{ "frame_index", "track_id", "vertices_cam_m": [[x, y, z], ...], "ok"?, "depth_gap_m"? }] }`.
- **JSONL**: first line `{ "type": "mesh_header", "backend", "faces" }`, then one mesh record per line.

Closed meshes are drawn single-sided (winding detected per mesh from its signed volume, so mirrored left hands work); open surfaces are drawn double-sided. Mesh gaps shorter than 0.2 s stay visible in the mesh lane but are not listed as events. MANO faces and vertices derived from footage are private: keep them out of the repo.

The synthetic demo uses a **stand-in mesh** (tubes around the skeleton) so the mesh view can be shown without licensed MANO assets. It is labelled as such and is not a model output.

Keys: `space` play/pause · `←/→` step one frame · `Home` jump to start. 3D view: drag to orbit, scroll to zoom, double-click to reset.

## Visual rules

- Wearer-left is orange `#d95926`, wearer-right is blue `#3987e5`, and other people's hands are gray `#898781`. The two hand colours pass the colour-blind and contrast checks on the dark surface `#1a1a19`.
- Reliability is shown by line style and opacity, never by a new hue. Green/red are used only for true/false masks, always with ✓/✕ text.
- Text is always in ink colours. A small colour key carries hand identity.
- Honesty labels are always visible: "Camera-space estimate (approx. lens model)", or "Hand-relative 3D estimates. Factory position and camera motion are not reconstructed."

## Next steps

1. Write `mesh_*.npz` from the WiLoR / HaMeR step in the format above (after inspecting one real model output), then load it with **Add results**.
2. Mirror this layout as a Rerun blueprint in `render.py` (demo artifact `.rrd`), using the same entity tree: `/video`, `/camera_space/hands/{side}`, `/hand_relative/hands/{side}`, `/metrics/{side}/*`, `/events`.
3. Point the page at the first real `landmarks.jsonl` once camera-space 3D lands. Check the lanes and events against the gold labels.
4. Replace the assumed 128° × 67° frustum with the calibrated lens model from `manifest.json`.
