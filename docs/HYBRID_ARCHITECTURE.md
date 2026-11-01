# Hybrid hand detection: architecture as built

The existing pipeline was extended in place: same modules, presets and outputs. Stages marked *off* were built, measured and switched off by default because they did not help.

```text
video → decode (packet-PTS timestamps) → 960 px RGB
  │
  ├─ MediaPipe HandLandmarker, VIDEO mode, 2 hands, thresholds 0.3 ........ model.Detector
  ├─ fewer than 2 hands → centre-crop rescue (IMAGE mode) ................... model.CropRescueDetector
  ├─ [accurate] reverse-time MediaPipe pass, merged without duplicates ........ parallel.BackwardPass
  └─ [hybrid] fewer than 2 hands AND a hand seen in the last 0.8 s is missing:  hybrid.HybridDetector
        RTMDet-nano hand boxes on 2×2 tiles (score ≥ 0.2), skip boxes on found hands
        gate: box near the missing hand (0.15 diagonals + half the box)
        (off) MediaPipe retry inside the box ............ dev: 0 hands recovered, 4 false
        RTMPose-m 2D keypoints (mean score ≥ 0.25) → handfit: depth from the median hand
        gate: wrist within 0.15 diagonals of the missing hand
  │
  ▼
tracker (tracking.IdentityTracker): Hungarian matching on wrist distance + shape + side
  ├─ box-link: a detection inside a just-missed track's box keeps that identity
  ├─ a just-missed track predicted onto an observed hand is reported lost (no ghost)
  ├─ side = running P(right) with per-path evidence weights:
  │    full frame 0.15, crop rescue 0, neutral score 0 (inherited); hysteresis 0.15; undecided = unknown
  └─ One Euro smoothing per track (raw values kept)
  │
  ▼
records: landmark_source (mediapipe | rtmpose), world_source (mediapipe_world | fitted_from_2d),
         side_source, provenance (fitted 3D = inferred)
  │
  ├─ quality windows, review queue ......................... quality.py
  ├─ whole-track side vote (identity.json) ................. identity.py
  ├─ camera-space 3D, ASSUMED lens, counted per 3D source .. lift.py
  └─ viewer: #track side · state · detection path · 3D source; low-poly mesh from lifted joints
```

## Presets

| Preset | Detector | Tracker | Use |
| --- | --- | --- | --- |
| `baseline` | MediaPipe defaults | original | Reproduces historical runs |
| `recall` | 0.3 thresholds + centre crop | box-link, side fix | **Default in the viewer** |
| `accurate` | `recall` + reverse-time pass | same | Offline, about 2× detector time |
| `hybrid` | `recall` + gated RTMPose fallback | same | Accuracy mode, about 3× detector time; needs `--extra hybrid` and `fetch-model --rtm` |

- **Fast mode** = `recall` (or `baseline`). **Accuracy mode** = `accurate` or `hybrid`.
- They cannot yet be combined (`hybrid` + reverse pass) without more measurement time.

## Why each choice (all made on dev; holdout run once)

- **RTMPose instead of MediaPipe-in-box.** MediaPipe's palm detector rejects in a crop what it rejects in the frame (0 of 20 boxed missed hands at threshold 0.3). RTMPose put the wrist on the labelled wrist for 19 of 20.
- **The track gate.** RTMPose scores on wrong boxes (rollers) overlap those on real hands. Proximity to a recently seen, now-missing hand separates them (8 real against 1 wrong at score ≥ 0.25).
- **No 3D invented.** RTMPose-only hands get hand-relative 3D from 2D plus a typical hand's depth, marked `fitted_from_2d` with provenance `inferred`. They get a mesh, but it is never counted as observed 3D.
- **Side from evidence, not position.** Screen position is never used; per-path weights and hysteresis come from [HANDEDNESS_ROOT_CAUSE](HANDEDNESS_ROOT_CAUSE.md).
