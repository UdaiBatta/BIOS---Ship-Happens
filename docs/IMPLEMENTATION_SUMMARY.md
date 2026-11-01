# Implementation summary

Current verification: 197 pipeline tests passed and 1 skipped; 42 of 42 backend tests passed. Hand posture is now the default view, and loading a run preserves the selected mode. Camera-space frames without accepted depth use a clearly labeled posture fallback; camera-space rejection masks remain unchanged.

Current status as of 1 Nov 2026: the browser viewer has workspaces, a resizable video/3D layout, playback, timeline inspection and event navigation. 3D offers Side/Top/Camera viewpoints, follow-hand centering, orbit, zoom and reset. Camera-space lift remains raw; image and hand-relative coordinates have filtered variants. The shipped pipeline smooths wrists with an offline RTS pass and finger offsets with One Euro filtering. Backend runs can generate bone-length-calibrated hand surfaces. Motion-event candidates are heuristic; face-only privacy flags are experimental. Current-session common accuracy is not measured because the local `labels_v2` inputs are missing. The CLI processing preset defaults to `baseline`; the backend UI defaults to `recall`.

The table below preserves the 31 Oct–1 Nov sprint record. Its numerical results are historical measurements from that work and have not been rerun in the current session. See the linked reports for their original methods and limitations.

| # | Workstream | Historical status | Evidence |
| --- | --- | --- | --- |
| 1 | Multi-video loading | Done | Root causes: no discovery while running; run list not tied to the selected video. Scan endpoint, video-first bar, upload, clear errors. [VIDEO_LOADING_DIAGNOSIS](VIDEO_LOADING_DIAGNOSIS.md) |
| 2 | Playback stutter | Done (measured without a GPU) | Overlay ≠ shown frame: 173/179 → 0/180; one clock (`requestVideoFrameCallback`); redraw per presented frame. Laptop not measured. [PLAYBACK_PERFORMANCE](PLAYBACK_PERFORMANCE.md) |
| 3 | Raw vs smoothed | Done | Earlier filter comparison: wrist error 28.7 → 48.1 px; the report also records the RTS wrist + One Euro finger result. [SMOOTHING_COMPARISON](SMOOTHING_COMPARISON.md) |
| 4 | Anatomical low-poly mesh | Done | 1,872 triangles, knuckles, domed palm, thenar and web, per-track size and bone lengths. [HAND_MESH_ARCHITECTURE](HAND_MESH_ARCHITECTURE.md) |
| 5 | Still-hand discovery | Tried, no gain | Periodic discovery with 3-check confirmation (`--discover-every`, off): dev recall unchanged 45/72, the still bare hand unchanged 17/30 |
| 6 | Same-side tracks | Done | 2+ records with one side are mostly lost leftovers (131 lost+observed frames). The weaker of two observed same-side hands is shown unknown: holdout pairs 31 → 3, wrong sides unchanged. Lost tracks listed as a note, not as hands |
| 7 | Honest depth | Done | Approximate camera-space under an assumed lens; see [EXPERIMENTAL_3D_STATUS](EXPERIMENTAL_3D_STATUS.md) |
| 8 | Other video families | Not measured | Label about 50 frames per family with `egohand annotation-set`, then `scripts/compare_baseline.py` |
| P1 | Timeline redesign | Done | Primary lanes + Unknown-side lane, events strip, zoom/pan/scrub, failure and reacquisition jumps, inspection panel, collapsed diagnostics. [TIMELINE_REDESIGN](TIMELINE_REDESIGN.md) |
| P4 | Industrial UX | Partly done | Workspaces, resizable split, 3D controls, states. Follow-hand camera, video search and full restyle were not part of that sprint. [INDUSTRIAL_UX_DESIGN](INDUSTRIAL_UX_DESIGN.md) |
| P5 | Evidence-linked events | Done (thresholds unvalidated) | Entry, exit, long gap, candidate hold and movement; evidence frames; Confirm/Reject stored and restored. [MOTION_EVENT_SCHEMA](MOTION_EVENT_SCHEMA.md) |
| P6 | Privacy flags | Experimental | Faces only; historical sample found false alarms and missed distant people. [PRIVACY_FEATURE_STATUS](PRIVACY_FEATURE_STATUS.md) |
| P7 | 3D-vs-video test, review-time pilot | Not run | Protocol: [USER_TEST_PROTOCOL](USER_TEST_PROTOCOL.md) |
| — | WiLoR / MANO | Not integrated | Licence, authorized assets and compute remain gates; mesh NPZ loading is a viewer capability. |
| — | Camera-motion compensation, monocular depth | Not started | [DEPTH_FEASIBILITY](DEPTH_FEASIBILITY.md), [TODO](TODO.md) |

Historical preset results and accuracy claims remain in [RESULTS_V2](RESULTS_V2.md) and [EXPERIMENT_RESULTS](EXPERIMENT_RESULTS.md). They describe provisional one-clip measurements, not current-session accuracy.
