# Submission guide

## Project details

- **Project:** MOTIONIQ
- **Category:** PS4 — 3D Hand Motion
- **Repository:** https://github.com/UdaiBatta/BIOS---Ship-Happens
- **Purpose:** turn head-mounted factory footage into inspectable hand-relative 3D posture estimates and timestamped motion data.

## Short project description (current)

MOTIONIQ processes head-mounted video locally and presents hand landmarks, short-term tracks, uncertainty states and review tools. The browser viewer supports synchronized video and landmark inspection, a 3D view with orbit, zoom and reset, a timeline, frame details, heuristic event review and exports. A generated hand surface is available for backend runs with camera-space landmarks; it is bone-length calibrated, but it is not a fitted MANO/WiLoR model. Motion events are inferred candidates with unvalidated thresholds. Face-only privacy flags are experimental review assistance. The current session's common accuracy has not been measured because the local `labels_v2` inputs are missing. Earlier single-clip measurements remain provisional historical results in [RESULTS_V2](RESULTS_V2.md). The camera-space lift assumes a lens model; depth is unvalidated. The system does not provide robot export or factory coordinates.

## Short project description (first milestone, historical)

MOTIONIQ is an offline computer-vision pipeline for inspecting hand motion in factory POV videos. It uses MediaPipe to estimate 21 image landmarks and 21 hand-relative 3D landmarks per detected hand, associates observations into short-term tracks, and exposes observed, predicted, lost and reacquired states. A synchronized viewer places the original footage beside 3D hand skeletons and tracking events. Raw and smoothed landmarks export to JSONL, CSV and NPZ for downstream analysis. The system runs on laptop CPU hardware and includes an optional, experimental crop-rescue detector for missed hands. The current implementation reconstructs hand-relative skeleton posture; it does not yet produce hand meshes or validated absolute factory coordinates.

## What is implemented

- Offline video processing with source presentation timestamps.
- MediaPipe Tasks Hand Landmarker, up to two hands by default, 21 landmarks per hand.
- Short-term identity assignment with spatial gates, motion, shape and soft handedness cues.
- Offline RTS wrist smoothing and One Euro finger-offset smoothing while preserving raw measurements.
- Explicit missing-data states; predicted 2D points never count as observed detections and contain no invented 3D articulation.
- Side-by-side H.264 video, synchronized Rerun replay and timestamped tracking events.
- Raw/filtered JSONL, CSV and NPZ exports, source/model hashes and run metadata.
- Evaluation tooling for annotated data. Current-session accuracy is not measured.

## Historical evidence (not remeasured in the current session)

The tested machine was an Apple M1 MacBook Air with 8 GB RAM. The comparison used 900 consecutive frames from the first 30 seconds of one supplied 1080p, 30 FPS factory clip. Forty clips were inventoried; only one interval from one clip was benchmarked.

| Configuration | Frames with observed hands | Total processing time | End-to-end FPS |
| --- | ---: | ---: | ---: |
| Plain index-ID baseline | 143 / 900 | 66.36 s | 13.56 |
| Persistent tracking + smoothing | 143 / 900 | 68.33 s | 13.17 |
| Tracking + smoothing + experimental crop rescue | 332 / 900 | 89.66 s | 10.04 |

These fractions describe observed-hand frame coverage, **not accuracy or recall**. Some frames contain no visible hands. More crop-rescue detections may include errors. The plain and persistent runs have identical raw observations; tracking does not manufacture new detections. Human-reviewed recall, landmark accuracy and identity-switch results are pending. No 3D accuracy or industrial productivity improvement has been measured.

See [the complete measured report](MILESTONE_REPORT.md) for inference latency, memory, validation and limitations.

## Five-minute demonstration outline

1. **0:00–0:35:** explain the factory POV problem and show a challenging clip.
2. **0:35–1:30:** show observed landmarks and synchronized hand-relative 3D posture.
3. **1:30–2:15:** pause at a specific timestamp and rotate the 3D view.
4. **2:15–3:00:** inspect a loss/reacquisition interval; explain prediction versus observation.
5. **3:00–4:00:** present the measured comparison and distinguish coverage from accuracy.
6. **4:00–4:40:** inspect exports and explain an engineer's motion-review workflow.
7. **4:40–5:00:** state the remaining limits: difficult hand poses, handedness mistakes, identity fragmentation, meshes and calibrated world coordinates.

## Submission checklist

Historical audit and experiment material is linked from [PRODUCT_BRIEF.md](PRODUCT_BRIEF.md) and [RESULTS_V2.md](RESULTS_V2.md). Use [DEMO_SCRIPT.md](DEMO_SCRIPT.md) for the current viewer click path. Do not present historical measurements as current-session accuracy.

The checked entries below record completed historical work; their measurements remain provisional and were not rerun in the current session.

- [ ] Current-session common accuracy measurement. The local `labels_v2` inputs needed for rescoring are missing.
- [x] Detection recovery chosen on dev and scored once on holdout (recall 0.24 → 0.50, precision 39/40; provisional labels, one clip).
- [x] Quality windows, review queue, segment export, Rerun quality timeline; flag evaluation and false-alarm burden reported.
- [x] Verified fast timestamp probe and per-stage timing.
- [ ] Process at least one clip from each other recording family (blocked here: Drive downloads not reachable from this environment).
- [ ] Ask the organizers the drafted questions in PRODUCT_BRIEF.md (lens intrinsics, QA framing, sharing of processed outputs).
- [ ] When the organizers answer, set `consent_status` and `retention_until` in `data/private/governance_mytronlabs.json` (currently `unknown` / null) and reprocess the demo runs with `--governance`. Only runs made with `--governance` (e.g. `runs/final_demo`) record governance; `motioniq retention-report runs` lists the rest as `governance_not_recorded`.
- [ ] Run the review-time pilot (protocol in DEMO_AND_QA.md) or present the benefit as untested.
- [ ] Confirm which local completed run is suitable for the demo; otherwise use the viewer preview and demonstrate processing explicitly.
- [ ] Record the five-minute demo from a locally approved run.
- [ ] A teammate reviews the labels: `motioniq label-review` → fill `data/private/label_review/review.csv` → `label-review-apply` → re-run the evaluation commands in RESULTS_V2 §8.
- [ ] Before any public copy: remove docs that name clips or describe the footage (RESULTS_V2, AGENT_CONTINUATION_PROMPT, REFERENCE_ARTIFACTS); keep the repository private while release assets are attached.

Historical checklist:

- [x] Working MediaPipe PS4 skeleton baseline.
- [x] Source code, dependency lock, setup instructions and automated tests.
- [x] Real-footage comparison with measured runtime and explicit limitations.
- [x] Cached 30-second processed demos and replay files prepared locally, outside repository content.
- [ ] Review annotations and evaluate recall, landmark error and identity consistency on representative held-out clips.
- [ ] Upload processed demo clips to the designated private submission folder.
- [ ] Provide judges repository access in the format required by the organizers; keep footage out of repository history.
- [ ] Prepare the required 5–6 slides and rehearse the five-minute presentation and three-minute Q&A.
- [ ] Verify the final form links from a judge-accessible account before submitting.

WiLoR/MANO fitting, robot export, camera-motion compensation and validated camera/world reconstruction remain unavailable. Motion-event thresholds and experimental face flags need labeled evaluation.
