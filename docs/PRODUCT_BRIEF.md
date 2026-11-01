# MOTIONIQ — product brief and status (PS4, revised 31 Oct 2026)

## Product

**MOTIONIQ reconstructs hand motion from factory POV footage and helps data teams find useful, uncertain and problematic segments for further review.**

```text
Video -> hand observations + hand-relative 3D -> task-specific quality signals
      -> timestamped review queue -> traceable structured exports + synchronized replay
```

Primary user: a data engineer preparing factory demonstrations for hand-motion analysis or robotics research. They should be able to answer:

| Question | Where the answer comes from |
| --- | --- |
| Where do we have usable hand-motion observations? | `quality/quality_windows.json` (`suitable`), `export-segments --status suitable` |
| Where does reconstruction fail or become uncertain? | `needs_review` windows and their reason codes |
| Which intervals should someone inspect first? | `quality/review_queue.csv`, ranked by a disclosed priority rule |
| What evidence caused a flag? | per-window `evidence` (coverage, gap seconds, new IDs, side changes, jumps, blur ratio, exposure, motion) |
| Which outputs are observed, predicted or unavailable? | `state`/`observed` per track sample; predictions are 2D-only, lost tracks have no coordinates |
| Can a result be traced to source frames and configuration? | source SHA-256, run id (manifest hash), frame ranges, quality-config digest in every export |

**Organizer context (condensed notes, not a transcript).** The organizer's company collects egocentric factory footage for physical-world AI. The notes mention dust, blur, harsh light, fast motion, unusual viewpoints and occlusion. They also mention unreliable hand tracking, deciding whether footage is usable, automated QA, possible privacy review, and turning large volumes into structured data. A figure of about 100 TB was mentioned. We treat it as context only; nothing here has been tested at that scale. These notes do not change the published rubric. Hand reconstruction (PS4) remains the deliverable, and the quality layer makes it more useful.

## Status audit

**A. Implemented and verified on real footage**
- MediaPipe 21-point image and hand-relative 3D landmarks, persistent short-term track IDs, explicit observed/predicted/lost/retired states, raw vs filtered exports (JSONL/CSV/NPZ), manifests with hashes, synchronized MP4 and Rerun replay. Re-run on this Linux host: identical timestamps to the M1 runs; detections differ on 57/900 frames (platform numerics), so every comparison below uses runs from this host.
- Verified fast timestamp path: packet PTS identical to decoded-frame timestamps on all 5,400 frames, checked automatically at runtime with fallback; per-stage timing in `metrics.json`.
- Split-aware labeling tool and an evaluator for recall/precision with intervals, recall by visibility and side, left/right confusion, ID changes, a wrist-gate audit and lists of missed hands and false positives.
- Quality signals, review queue, segment export and a quality timeline in Rerun. These run end-to-end on real footage; the review experiment is still pending (see B).
- Reliability shown in the replay: per-track state lanes, side probability, inferred `missing_reason` (measured: often wrong at the image edge), units and coordinate frames in view titles.
- Teach-back helpers: same-moment flat-vs-3D image (`compare`) and a `steps.json` sidecar with reviewer sign-off.
- Governance and lens provenance in `manifest.json` (schema 0.4), validated before processing, plus a retention report that never deletes anything.
- Per-frame output validates against `motioniq_frame.schema.json` (`motioniq validate`).
- Capture conditions and exclusions in a `conditions.json` sidecar, with evaluation sliced by condition.
- Continuity metrics: fragments per labeled hand; predicted-run and bridged-gap statistics.
- Frozen definitions in [DEFINITIONS.md](DEFINITIONS.md); deferred work in [TODO.md](TODO.md); refreshed build prompt in [BUILD_PROMPT.md](BUILD_PROMPT.md).
- 82 automated tests.

**B. Implemented, not adequately validated**
- **Labels:** 96 frames / 150 hands, all **provisional**. A single annotator from the coding session read them visually from grid overlays; they have **not been independently reviewed by a person**. Every number computed from them is stamped provisional.
- **Detection candidates:** thresholds 0.3 plus the downscaled center crop (the chosen candidate), full-resolution tiles, track-guided crops, anti-aliased crops. Measured on dev and holdout from **one clip and one recording family**.
- **Quality thresholds:** set by inspecting the development interval; not validated on other clips.
- **Offline whole-track side vote and aspect-correct tracker distance:** available as options, no clear benefit measured.
- **Camera-space PnP lifting** under an **assumed** fisheye lens (`motioniq lift`, separate replay view). Synthetic tests pass. On footage, depth changes by ±25% across plausible FOV assumptions and is **unvalidated**.

**C. Proposed, not implemented**
- Bone-length calibration and 3D smoothing in camera space, meshes (WiLoR/HaMeR), robot/gripper export, SLAM or head-rotation stabilization.
- Semantic action recognition. Privacy candidate flags (faces, screens, text).
- A human review-time experiment.

**D. Blocked**
- Independent human review of the labels needs a team member.
- The other 39 clips and three recording families: Drive links exist, but this environment's network policy blocks the Drive download host.
- Lens calibration or intrinsics need an answer from the organizers.
- GPU and MANO assets for meshes.
- The actual remaining deadline needs confirmation from the team.

## Priorities, timeboxes and cuts

| Priority | Item | Status / timebox |
| --- | --- | --- |
| P0 | Keep PS4 reconstruction and replay working | Done. Default CLI behavior unchanged (B0). |
| P0 | Detection improvement chosen on dev, reported once on holdout | Done (provisional labels). Candidate flags documented; default not switched until labels are reviewed. |
| P0 | Explainable quality layer from cached runs | Done (heuristic). |
| P1 | Review queue, segment export, Rerun timeline | Done. |
| P1 | Evidence tables, demo script, Q&A | Done: [RESULTS_V2](RESULTS_V2.md), [DEMO_AND_QA](DEMO_AND_QA.md). |
| P1 | Human label review, then re-score | **Needs a person, about 45 min.** Highest-value next step. |
| P1 | Review-time pilot (ordinary video vs queue) | Protocol written; **not run** (needs participants). |
| P2 | Context events (hands enter/leave, activity intervals) | Partly covered by `tracking_events.csv` and window statuses; no semantic actions. |
| Cut | Privacy flags | Cut: no labeled evaluation set and no time to measure misses and false alarms. Future work. |
| Cut | Meshes, SLAM, robot export, bone calibration | Cut: gates not met (no GPU/MANO; lens unknown; depth unvalidated). |

**Feature freeze.** No new features after the quality layer; the remaining time goes to label review, re-scoring and the demo. If the team confirms a deadline, put the freeze at least 4 hours before submission.

## Draft questions for the organizers (not sent)

> 1. For PS4, will judges credit a quality/review layer (usable vs uncertain hand-motion segments, timestamped review queue) as part of "industrial usefulness", or should it be presented strictly as supporting the 3D hand reconstruction?
> 2. Can you share the camera intrinsics or lens model (fisheye type, field of view) for the head-mounted camera? Without them, any metric depth we show is an assumption.
> 3. May processed outputs derived from the official clips (overlay videos, Rerun recordings) be shown to judges in a private submission folder, and what retention or deletion rules apply after the event?
