# Five-minute local viewer demo

Use an authorized local video and keep the server bound to `127.0.0.1`. Keep footage, derived data and screenshots private; do not place them in public slides or repositories.

## 1. Start and select a video

Run `scripts/run_local.ps1` on Windows or `scripts/run_local.sh` on macOS/Linux. The launch script starts the viewer, local backend and worker. In the Backend row, select a registered video. The viewer loads its newest completed run automatically. If it has no completed run, it shows a still preview; choose the run interval and preset, then click **Process** to queue processing. Processing is explicit.

Start the demonstration in **Hand posture**, the default. It shows wrist-centered hand-relative geometry even when the assumed-lens camera estimate is rejected. **Camera space · experimental** is optional; its fallback is labeled and does not invent camera placement. **Mesh / Mesh + skeleton** work in posture and camera views. Explain that Side score means left/right classifier support, while landmark confidence is uncalibrated.

If FFmpeg is outside PATH, set `MOTIONIQ_FFMPEG_DIR` to its `bin` directory before launching. Keep the laptop on AC power. A prepared run must be selected before presenting; do not rely on live processing. The final demo-run identifier will be kept in ignored `deliverables/demo-run.txt` once preparation passes.

Run `powershell -File scripts/preflight.ps1 -RunId <prepared-run-uuid>` or `bash scripts/preflight.sh --run <prepared-run-uuid>`. A passing check does not replace testing playback and the private backup recording.

Open `http://127.0.0.1:8000/?run=<prepared-run-uuid>` to load the prepared run directly. Its UUID is in the ignored local handoff file; do not put private run identifiers in public slides.

## 2. Six-slide outline

Use `slides/MOTIONIQ.pptx` and its PDF copy. Both remain drafts until accuracy inputs, the final speed measurement and a teammate's readthrough are complete.

1. The data engineer's problem: usable, uncertain and missing hand motion.
2. Pipeline: detection presets, explicit tracking states, offline smoothing, estimated 3D, review and exports.
3. Live-demo cues: synchronization, viewpoints, failures and provenance.
4. Accuracy by preset: show measured denominators only after human labeling. Until then the cells say not measured.
5. Laptop efficiency and review usefulness: distinguish the measured interval from the unrun pilot.
6. Limits: assumed lens, generated surface, uncompensated camera motion and label status.

## 3. Planned five-minute timing

These are rehearsal targets, not measured presentation times.

| Time | Click path and point |
| --- | --- |
| 0:00–0:30 | Problem slide: identify the reviewer and the decision about usable seconds. |
| 0:30–1:15 | Backend video selection → newest prepared run → Review. Play and pause synchronized video and landmarks. |
| 1:15–2:00 | Skeleton / Mesh / Mesh + skeleton → Side / Top / Camera → Follow hand → Raw / Smoothed → Reset view. Explain estimated geometry. |
| 2:00–3:00 | Timeline seek and zoom → F / R → event list → frame evidence. Explain candidate review without treating heuristic flags as truth. |
| 3:00–3:45 | Analysis → available exports; Diagnostics → state/provenance details. Predictions are 2D only; lost data are missing. |
| 3:45–4:30 | Results slides: distinguish coverage from accuracy and state missing measurements. |
| 4:30–5:00 | Limits slide and next experiments. |

## 4. Walkthrough and fallback

1. In the **Review** workspace, show the synchronized video and 2D landmarks. Point out that observed, predicted and lost states are distinguished, and predictions have no 3D landmarks.
2. Drag the video/3D divider to adjust the layout. Choose **Side / Top / Camera**, toggle **Follow hand**, drag to orbit and scroll to zoom; click **Reset view** or double-click to reset. State whether the display is approximate camera-space or hand-relative 3D. Camera-space depth uses an assumed lens and is unvalidated.
3. Click a timeline lane to seek and inspect the frame details. Use the failure and reacquisition buttons, or **F** and **R**, to jump between corresponding tracking events. Explain that the event list contains heuristic/inferred candidates and that any review status is a human decision.
4. Switch to **Analysis** to focus on timeline, available signals, events and export. **Diagnostics** exposes additional pipeline information. Do not imply that hidden signal data or a measurement exists when its chart is absent.
5. Show the available exports and traceability fields. Do not claim that this viewer measures accuracy, user benefit, productivity, contact or force.

Fallback order: use the prepared local run without network; if playback fails, play the private screen-capture backup from local storage or USB; if that fails, open the file viewer's synthetic demo and state clearly that its values are synthetic. The human-recorded backup and cold-start rehearsals are still pending.

## 5. Claims and Q&A rehearsal

- Current-session common accuracy has not been measured; local `labels_v2` rescoring inputs are missing. Earlier provisional results are historical and documented in [RESULTS_V2.md](RESULTS_V2.md).
- Generated hand surfaces are a visualization built from landmarks. They are not fitted MANO/WiLoR meshes. The camera-space estimate is not validated factory/world geometry.
- Motion events are inferred candidates with unvalidated thresholds. Privacy flags cover faces only and are experimental review assistance.
- Coverage is not recall. Common-clip accuracy and independent label agreement need human annotations. The review-time benefit has not been measured.

For the live rehearsal, ask questions one at a time and score each answer for correctness and honesty. Cover unseen clips; matching rules; wrong sides; assumed-lens depth; generated versus fitted mesh; failure states; runtime; privacy; the contribution beyond MediaPipe; factory use; camera motion; and the next week of work. Use current [common-clip results](COMMON_CLIPS_RESULTS.md), [performance](PERFORMANCE_REPORT.md) and [limitations](KNOWN_LIMITATIONS.md). Earlier answers in [DEMO_AND_QA](DEMO_AND_QA.md) contain historical measurements and must not be recited as newly verified results.
