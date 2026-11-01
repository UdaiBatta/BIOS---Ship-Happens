# Implementation summary: debugging and UX sprint (31 Oct – 1 Nov 2026, branch `udai-s1`)

**Tests:** 159 pipeline tests pass, 42 backend tests pass. **Git history:** no media, data or model files (`scripts/check_history.sh`).

| # | Workstream | Status | Evidence |
| --- | --- | --- | --- |
| 1 | Multi-video loading | **Done** | Root causes: no discovery while running; run list not tied to the selected video. Scan endpoint, video-first bar, upload, clear errors. [VIDEO_LOADING_DIAGNOSIS](VIDEO_LOADING_DIAGNOSIS.md) |
| 2 | Playback stutter | **Done** (measured without a GPU) | Overlay ≠ shown frame: 173/179 → 0/180; one clock (`requestVideoFrameCallback`); redraw per presented frame. Laptop not measured. [PLAYBACK_PERFORMANCE](PLAYBACK_PERFORMANCE.md) |
| 3 | Raw vs smoothed | **Done** | Old filter lagged (wrist error 28.7 → 48.1 px). Offline RTS wrist + One Euro fingers: 30.1 px dev, 26.6 px holdout, jitter halved. [SMOOTHING_COMPARISON](SMOOTHING_COMPARISON.md) |
| 4 | Anatomical low-poly mesh | **Done** | 1,872 triangles, knuckles, domed palm, thenar and web, per-track size and bone lengths. [HAND_MESH_ARCHITECTURE](HAND_MESH_ARCHITECTURE.md) |
| 5 | Still-hand discovery | **Tried, no gain** | Periodic discovery with 3-check confirmation (`--discover-every`, off): dev recall unchanged 45/72, the still bare hand unchanged 17/30 |
| 6 | Same-side tracks | **Done** | 2+ records with one side are mostly lost leftovers (131 lost+observed frames). The weaker of two observed same-side hands is shown unknown: holdout pairs 31 → 3, wrong sides unchanged. Lost tracks listed as a note, not as hands |
| 7 | Honest depth | **Done** | "approx. camera-space (assumed lens)", "≈ m est." [EXPERIMENTAL_3D_STATUS](EXPERIMENTAL_3D_STATUS.md) |
| 8 | Other video families | **Not measured** | No labels for other families; label about 50 frames per family with `egohand annotation-set`, then `scripts/compare_baseline.py` |
| P1 | Timeline redesign | **Done** | Primary lanes + Unknown-side lane, events strip, zoom/pan/scrub, failure and reacquisition jumps, inspection panel, collapsed diagnostics. [TIMELINE_REDESIGN](TIMELINE_REDESIGN.md) |
| P4 | Industrial UX | **Partly done** | Workspaces, resizable split, 3D controls, states. Not done: follow-hand camera, video search, full restyle. [INDUSTRIAL_UX_DESIGN](INDUSTRIAL_UX_DESIGN.md) |
| P5 | Evidence-linked events | **Done** (thresholds unvalidated) | Entry, exit, long gap, candidate hold and movement; evidence frames; Confirm/Reject stored and restored. [MOTION_EVENT_SCHEMA](MOTION_EVENT_SCHEMA.md) |
| P6 | Privacy flags | **Experimental, not useful yet** | Faces only: 2/2 candidates were false alarms, distant people missed. [PRIVACY_FEATURE_STATUS](PRIVACY_FEATURE_STATUS.md) |
| P7 | 3D-vs-video test, review-time pilot | **Not run** | Protocol ready: [USER_TEST_PROTOCOL](USER_TEST_PROTOCOL.md) |
| — | WiLoR / MANO | **Blocked** | Licence, GPU and weights; download hosts blocked. Integration path exists (mesh NPZ) |
| — | Camera-motion compensation, monocular depth | **Not started** | [DEPTH_FEASIBILITY](DEPTH_FEASIBILITY.md), [TODO](TODO.md) |

**Presets (unchanged):**
- `recall` (default);
- `accurate` (best holdout F1 0.730);
- `hybrid` (experimental, precision 0.887);
- `baseline`.

`recall`, `accurate` and `hybrid` now also use the left/right fix, the same-side display rule and the new smoothing.

**All accuracy numbers:** one clip, provisional labels.
