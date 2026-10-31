# EgoHand Twin: viewer prototype

`prototype/index.html` is a single offline page. Double-click it to open it in Chrome or Firefox. It needs no server, makes no network requests and uses no libraries.

> Every value in the default demo is **synthetic**. The page shows a "SYNTHETIC DATA · not measured" badge until you load a real file.

## What's on screen

| # | Panel | What it shows | Pattern borrowed from |
|---|---|---|---|
| 1 | Video + 2D skeleton | Source frame (or a placeholder) with each hand's 21 points. Observed hands are solid, predicted hands are dashed (2D only), and reacquired hands get a ring. Each label gives side, state and the detection path (full frame / tile / guided crop / hand detector) | Rerun MediaPipe example |
| 2 | 3D hands | **Ours:** both hands in camera space (metres) with the camera frustum, the 0.2–0.9 m plausibility band, 2 s wrist trails and a two-finger gripper that follows the wrist and opens with the grip aperture. **Baseline:** MediaPipe hand-relative 3D at arbitrary spacing. Hands that are predicted or lost never get 3D | Rerun / HOT3D viewer, robot-export story |
| 3 | Timeline | Per-hand breakdown (tracked / predicted / not tracked), then reliability lanes: left hand, right hand, other people, low-blur mask, 3D-valid mask. Hover for values; click to seek | HOT3D quality masks, Invisible AI cycle breakdown |
| 4 | Signals | Reprojection error (px), grip aperture (m) and wrist depth (m). Each signal has its own axis, and the crosshair tooltip covers both hands | LeRobot visualiser, Foxglove plots |
| 5 | Events | Lost, reacquired, predicted, blur, 3D-not-valid and implausible-depth events. Click to jump. "Problems only" filter | Twelve Labs result list, Drishti Trace |
| — | Frame details | Table view of the current frame: state, detection path, depth, aperture, reprojection, bone-length CV, P(right), confidence, provenance | Accessibility / evidence |
| — | Export | Frames JSONL (schema v1), events CSV, **Aria-compatible CSV** (landmarks remapped to Aria order, palm centre added). LeRobot and `.rrd` exports come from the pipeline | Project Aria MPS, LeRobot |

Header chips: coverage is computed from the loaded file and labelled as coverage, not accuracy. Recall and FPS stay `[MEASURE]` until they are measured. The 3D-mode chip always states what the 3D is.

## Using real outputs (stays on the laptop)

- **Load JSONL:** one `egohand_twin_frame` record per line (see `../schema/`). Invalid lines are skipped, and the page says how many. A predicted or lost hand that carries 3D breaks the schema rule, so the page shows it as 2D only and warns you.
- **Load video:** plays a local clip in sync, using `timestamp_s`. The file is never uploaded.
- Do not commit real outputs or screenshots of real footage. `*.jsonl` and media files are already git-ignored.

Keys: `space` play/pause · `←/→` step one frame · `Home` jump to start. 3D view: drag to orbit, scroll to zoom, double-click to reset.

## Visual rules

- Wearer-left is orange `#d95926`, wearer-right is blue `#3987e5`, and other people's hands are gray `#898781`. The two hand colours pass the colour-blind and contrast checks on the dark surface `#1a1a19`.
- Reliability is shown by line style and opacity, never by a new hue. Green/red are used only for true/false masks, always with ✓/✕ text.
- Text is always in ink colours. A small colour key carries hand identity.
- Honesty labels are always visible: "Camera-space estimate (approx. lens model)", or "Hand-relative 3D estimates. Factory position and camera motion are not reconstructed."

## Next steps

1. Mirror this layout as a Rerun blueprint in `render.py` (demo artifact `.rrd`), using the same entity tree: `/video`, `/camera_space/hands/{side}`, `/hand_relative/hands/{side}`, `/metrics/{side}/*`, `/events`.
2. Point the page at the first real `landmarks.jsonl` once camera-space 3D lands. Check the lanes and events against the gold labels.
3. Replace the assumed 128° × 67° frustum with the calibrated lens model from `manifest.json`.
