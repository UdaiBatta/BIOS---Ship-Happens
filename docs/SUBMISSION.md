# Submission guide

## Project details

- **Project:** EgoHand Twin
- **Category:** PS4 — 3D Hand Motion
- **Repository:** https://github.com/UdaiBatta/BIOS---Ship-Happens
- **Purpose:** turn head-mounted factory footage into inspectable hand-relative 3D posture estimates and timestamped motion data.

## Short project description

EgoHand Twin is an offline computer-vision pipeline for inspecting hand motion in factory POV videos. It uses MediaPipe to estimate 21 image landmarks and 21 hand-relative 3D landmarks per detected hand, associates observations into short-term tracks, and exposes observed, predicted, lost and reacquired states. A synchronized viewer places the original footage beside 3D hand skeletons and tracking events. Raw and smoothed landmarks export to JSONL, CSV and NPZ for downstream analysis. The system runs on laptop CPU hardware and includes an optional, experimental crop-rescue detector for missed hands. The current implementation reconstructs hand-relative skeleton posture; it does not yet produce hand meshes or validated absolute factory coordinates.

## What is implemented

- Offline video processing with source presentation timestamps.
- MediaPipe Tasks Hand Landmarker, up to two hands by default, 21 landmarks per hand.
- Short-term identity assignment with spatial gates, motion, shape and soft handedness cues.
- One Euro smoothing while preserving raw measurements.
- Explicit missing-data states; predicted 2D points never count as observed detections and contain no invented 3D articulation.
- Side-by-side H.264 video, synchronized Rerun replay and timestamped tracking events.
- Raw/filtered JSONL, CSV and NPZ exports, source/model hashes and run metadata.
- Evaluation against explicitly reviewed annotations, including precision/recall and sampled identity changes.
- Eleven focused automated tests.

## Verified evidence

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

Current status (v2): see [PRODUCT_BRIEF.md](PRODUCT_BRIEF.md) for the audit, [RESULTS_V2.md](RESULTS_V2.md) for measurements and [DEMO_AND_QA.md](DEMO_AND_QA.md) for the demo and Q&A. The short description above remains accurate. Add one sentence: "A heuristic quality layer marks each second as suitable, needs review or insufficient evidence for hand-motion inspection and produces a timestamped review queue and traceable segment exports."

- [x] Split-aware dev/holdout labels: 96 frames, 150 hands. **Provisional — independent human review still required.**
- [x] Detection recovery chosen on dev and scored once on holdout (recall 0.24 → 0.50, precision 39/40; provisional labels, one clip).
- [x] Quality windows, review queue, segment export, Rerun quality timeline; flag evaluation and false-alarm burden reported.
- [x] Verified fast timestamp probe and per-stage timing.
- [ ] A team member reviews `labels_v2_provisional.json` (uncertain-side and truncated hands first), sets `reviewed=true` only after review, and re-runs the commands in RESULTS_V2 §8.
- [ ] Process at least one clip from each other recording family (blocked here: Drive downloads not reachable from this environment).
- [ ] Ask the organizers the drafted questions in PRODUCT_BRIEF.md (lens intrinsics, QA framing, sharing of processed outputs).
- [ ] When the organizers answer, set `consent_status` and `retention_until` in `data/private/governance_mytronlabs.json` (currently `unknown` / null) and reprocess the demo runs with `--governance`. `egohand retention-report runs` currently lists 34 of 35 runs as `governance_not_recorded` (all created before schema 0.4).
- [ ] Run the review-time pilot (protocol in DEMO_AND_QA.md) or present the benefit as untested.
- [ ] Record the demo from the chosen-configuration run with `--quality` replay.

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

WiLoR/MANO integration remains an unrun feasibility investigation. Camera tracking and world-space reconstruction are optional future gates. Neither is presented as completed functionality.
