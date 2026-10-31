> **Historical baseline (first milestone, measured on an M1 MacBook Air).** Kept unchanged for comparison. Current results are in [RESULTS_V2.md](RESULTS_V2.md); on the Linux test host the same plain run observes 164/900 frames instead of 143/900 (identical timestamps; MediaPipe output differs by platform).

# First functioning milestone — 31 October 2026

**Status:** the MediaPipe PS4 minimum works on real supplied factory footage. Source video, 2D landmarks and hand-relative 3D skeletons are synchronized; raw and filtered estimates export to JSONL/CSV/NPZ. Persistent IDs, explicit missing-data states, timestamped tracking events and Rerun replay are implemented. This is not a validated accuracy result or a finished hackathon submission.

## What was actually tested

- Connected Drive inventory: 40 clips, approximately 4.35 GB. One authorized clip was downloaded privately.
- Tested source: 1920×1080 HEVC, 30 FPS, 180 seconds. The comparison uses only its first 30 seconds: 900 consecutive frames, no skipping. This is one interval from one clip, not a representative benchmark of all 40 clips.
- Host: Apple M1 MacBook Air, 8 GB unified memory, macOS 26.6.2. Python 3.12.13; MediaPipe 0.10.35, OpenCV contrib 5.0.0.93, NumPy 2.5.4, SciPy 1.18.1, Rerun 0.29.2. CPU inference was requested; CUDA hardware was not available on this host.
- Official float16 Hand Landmarker task bundle, version 1; source and model SHA-256 hashes are recorded in each private run manifest. Inference input width is 960 pixels; detection/presence/tracking thresholds are 0.5.
- All three runs generate the same 1600×900, 30 FPS H.264 preview and a Rerun recording. Rendering, source PTS inspection, setup and exports are included in reported processing time. Downloads and Python startup/imports are excluded. These are single runs on a working laptop, not controlled repeated performance trials.

## Measured results

| Configuration | Frames with ≥1 observed hand | Observed frame fraction | Processing time | End-to-end FPS | Inference FPS | Inference p95 | Sampled peak process RSS |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Index IDs, no smoothing | 143 / 900 | 15.89% | 66.36 s | 13.56 | 50.38 | 37.78 ms | 336.7 MB |
| Persistent IDs + smoothing | 143 / 900 | 15.89% | 68.33 s | 13.17 | 50.39 | 37.67 ms | 326.8 MB |
| Persistent IDs + smoothing + experimental crop rescue | 332 / 900 | 36.89% | 89.66 s | 10.04 | 22.79 | 65.18 ms | 382.4 MB |

Coverage is **not recall, precision, landmark accuracy or mesh quality**. The interval includes hands leaving the image, so the total frame count is not a hand-recall denominator. More detections may include incorrect estimates. Inference FPS excludes video decoding, rendering and exports and must not be presented as real-time application throughput. Sampled RSS may miss short peaks and excludes a separately launched viewer.

The plain and persistent runs have identical source timestamps and identical raw observed landmarks on all 900 frames, verified coordinate-by-coordinate. Tracking/smoothing does not create additional observations. Persistent tracking produced 16 short-term IDs and 28 proposed reacquisitions. Crop rescue produced 19 IDs and 67 proposed reacquisitions. These are tracker decisions, not validated identity recovery or identity-switch scores.

## Quality checks and observed limitations

- Eleven focused tests pass: reordered results, soft handedness, a controlled crossing, short occlusion/reacquisition, distant/expired re-entry, raw preservation, filter reset, timestamp ordering, crop coordinate restoration, label/source mismatch and predicted-data exclusion from recall.
- Real output readback verifies increasing timestamps, unique track IDs within frames, 21×3 observed landmark arrays, absent 3D values for non-observed tracks, CSV parsing, and NPZ loading without pickle.
- FFprobe confirms 900-frame, exactly 30-second, 1600×900 H.264 outputs. Rerun's `rrd verify` successfully loads the recordings.
- Browser visual QA confirms source frame 180 at 6.000 seconds beside both observed 3D skeletons, plus pause/time selection. A native screenshot attempt failed because this desktop session requested a 20,000-pixel-wide window exceeding the renderer's 16,384-pixel limit. The local browser viewer works and is the verified playback path on this host.
- Visual QA exposed an off-screen layout risk when arbitrary display offsets depended on increasing track IDs. Display positions now use two bounded slots and an explicit orbit camera. `replay_review.rrd` files rebuild the same cached observations with that layout, without new inference. Benchmark timings above refer to the original inference runs and were not remeasured after this display-only correction.
- MediaPipe misses visible hands during motion blur, back-of-hand poses and contact with a cloth. Handedness can be wrong. Short-term IDs fragment when detections disappear. These problems remain and are not hidden by predictions.
- A 10-frame diagnostic found center crops useful on several missed frames; the optional rescue was then benchmarked on the same development interval. This is development-set tuning, not holdout evidence. Its false positives, duplicate suppression and effects on handedness require annotation.
- 3D is estimated hand-relative posture. Display spacing is arbitrary. There is no validated absolute hand translation, factory frame, inter-hand distance, calibrated trajectory or 3D error measurement.

## Private artifacts on this machine

- `runs/baseline_30s/`: plain comparison.
- `runs/persistent_30s/`: primary baseline with persistent tracking and smoothing.
- `runs/rescue_30s/`: experimental crop-rescue comparison.
- Use `replay_review.rrd` in those directories for the visually checked layout. The original `replay.rrd` files are retained as benchmark artifacts.
- `runs/viewer_qa/browser_replay.jpg`: verified browser replay at six seconds.
- `data/private/drive_inventory.json`: full inventory; not included in public source.
- `data/private/annotations_first30/`: sampled frames and an unreviewed label template. The evaluator rejects it until explicitly reviewed and completed.

All source footage and derived motion/visual artifacts are ignored by Git and excluded from the source bundle.

## Next decisions

1. Human-review representative wrist/hand identity labels and joint labels; reserve untouched clips from the other recording families. Measure detector recall and sampled ID switches, then tune the tracker. Do not make the experimental rescue the default based on coverage alone.
2. Verify an actual GPU host and authorized MANO assets before the separate WiLoR benchmark described in `WILOR_FEASIBILITY.md`. No mesh inference has run.
3. Only after accuracy evidence, consider camera tracking; camera pose alone does not recover hand depth or metric scale.
4. Prepare the public source repository, private processed-clip submission, 5–6 slides and a rehearsed five-minute demo after these gates. None has been published by this milestone.
