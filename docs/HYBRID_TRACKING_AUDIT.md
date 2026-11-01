# Hybrid tracking audit (PS4 MOTIONIQ, branch `udai-s1`)

Scope: the application on this branch: Python pipeline `src/motioniq`, Django backend `backend/`, and the teammate's viewer `frontend/prototype`. This is the PS4 application running on the team laptop. `Bios-Hackathon` and the PS2/Therblig work are not part of this repository and were not touched.

- Known-working revision before this work: `0f50e26`.
- All numbers are on one clip (`mytronlabs-000060-016`), with provisional labels: dev 0–30 s, holdout 60–150 s.

## 1. The path a frame takes

| Step | Code | Input → output | Coordinates | State across frames |
| --- | --- | --- | --- | --- |
| Decode | `pipeline.process`, `parallel._detect_chunk` | file → BGR frame, PTS | source pixels, packet-PTS timestamps (kept) | sequential decode, no seeking |
| Resize | same | 1920×1080 → 960×540 RGB (`--max-width`) | inference pixels | none |
| MediaPipe | `model.Detector` (Tasks HandLandmarker, VIDEO mode, `num_hands=2`, CPU) | RGB → ≤2 × (21 image xyz, 21 world xyz, handedness label + score) | image: normalised x, y and relative z; world: metres, hand-relative | MediaPipe's internal ROI tracking (VIDEO mode) |
| Centre-crop rescue (`recall`) | `model.CropRescueDetector` | when < 2 hands: IMAGE-mode MediaPipe on the centre-bottom crop, mapped back by `map_crop_detection` | same | none |
| Reverse-time pass (`accurate`) | `parallel.BackwardPass` | second VIDEO-mode pass in reverse per 300-frame segment; non-duplicate hands added | same | per segment |
| Hybrid (`hybrid`, experimental) | `hybrid.HybridDetector` | RTMDet boxes → MediaPipe in the box → RTMPose 2D + `handfit` depth; track-gated | same; RTMPose points in inference pixels → normalised | memory of hands returned in the last 0.8 s |
| Tracker | `tracking.IdentityTracker` | detections → records (track id, state, side, smoothed 2D/3D) | same | tracks, velocity, running P(right), One Euro filters |
| Side shown | `record()["side"]`; viewer `anatomical_side` | running P(right) with hysteresis; viewer replaces it with the whole-track vote from `identity.json` when loaded | — | per track |
| 3D | `lift.lift_run` | PnP of world landmarks onto image points under an ASSUMED equidistant fisheye (HFOV 150°) | camera metres (x right, y down, z forward), depth unvalidated | none |
| Mesh | `frontend/prototype/hand-mesh.js` | 21 camera-space joints → low-poly capsules + palm | camera metres | none; a visual skin, not a fitted hand model |
| UI | `index.html` + `backend-connector.js` | run files + proxy video | — | — |

## 2. Confirmed defects (reproduced, measured and fixed)

| # | Defect | Source | Evidence | Fix | Result |
| --- | --- | --- | --- | --- | --- |
| 1 | A hand's shown side flips inside one track (the cloth hand "Wearer left → right") | **Identity**: the running P(right) took every detection's handedness at weight 0.15. Centre-crop-rescue handedness is unreliable (holdout 10/17 correct vs full frame 26/32), and the side flipped at exactly 0.5 | Holdout: 7 of 8 labelled flips happened inside one track | Crop detections carry no side evidence (the track keeps its side); the shown side changes only past P(right) 0.5 ± 0.15. Chosen on dev, checked once on holdout | Holdout: wrong sides 11 → 5 and 11 → 7; labelled Left↔Right flips 8 → 2 and 10 → 2; flicker within tracks 29 → 3 and 36 → 4. Undecided tracks now say `unknown` (12 and 6 of 49/54) instead of guessing |
| 2 | A "predicted" ghost skeleton drawn over a hand observed in the same frame, often with the other side | **Tracking/rendering**: a just-missed duplicate track kept being drawn | Ghost frames: dev 1, holdout 10 | Such a track is reported `lost`, and a detection inside a just-missed track's box keeps that identity (`--box-link`) | Dev 1 → 0, holdout 10 → 6; observations unchanged |
| 3 | Hybrid gave no recall gain and 11 false positives | **Detection fusion**: the RTMPose score cut-off of 0.45 was set without data, and recovery ran anywhere in the frame | Of 36 missed dev hands, RTMDet boxed 20 and RTMPose put the wrist on the label for 19, but only 1 scored ≥ 0.45. Wrong boxes (rollers) score as high as real hands | Cut-off 0.25 plus a track gate (recover only near a hand seen in the last 0.8 s that is missing now) | See [EXPERIMENT_RESULTS](EXPERIMENT_RESULTS.md) |
| 4 | RTMPose-only hands (handedness score 0.5) pulled their track's P(right) towards 0.5 | **Identity** | By construction | Zero-weight evidence: the side is inherited from the track (`side_source: inherited_from_track`) | Test `test_handedness.py` |
| 5 | Fitted 3D for RTMPose-only hands was not distinguishable from MediaPipe 3D | **3D provenance** | By construction | Records carry `landmark_source`, `world_source` (`mediapipe_world` / `fitted_from_2d`), and provenance `inferred` for fitted 3D; lift summary counts by source; viewer label says "3D fitted from 2D" | Test `test_3d_availability.py` |

## 3. Confirmed limitations (reproduced, not fixed)

- **Still hands are missed more often.** Holdout: found in 10/19 samples where the hand barely moved, against 37/53 moving. The dev bare left hand (back of the hand to the camera) is found 14/30 with `recall` and 18/30 with `accurate`. Likely cause: MediaPipe's palm detector sees almost the same image every frame, so a rejected hand stays rejected. The reverse-time pass helps on dev; nothing tested helps the still holdout samples (11/19 with `accurate`).
- **Two hands with the same side.** This happens in 69/165 two-hand holdout frames (only 4 are the same hand detected twice). Forcing one-left/one-right helped on dev but not on holdout, so it was not adopted. Most of these frames are unlabelled.
- **Labels on the cloth hand.** MediaPipe's landmarks over the cloth are often wrong even when a hand is reported. This is a landmark-model limitation; the 2D point accuracy (PCK) needs more landmark labels than the 23 labelled hands available.

## 4. Verified conventions

- **Handedness mirroring.** MediaPipe's label matches the wearer's side without flipping on this camera: 25 correct vs 8 mirrored on dev ([RESULTS_V2 §4](RESULTS_V2.md)). No preprocessing step flips images; the crops do not flip.
- **RTMPose keypoint order.** It matches MediaPipe's. On 60 confident MediaPipe hands, every RTMPose index lands nearest the same MediaPipe index (21/21). The median gap is 0.02–0.07 hand sizes.
- **RTM preprocessing.** It matches the exported pipelines: RTMDet BGR input, 320×320 letterbox padded with 114, BGR mean/std, NMS inside the ONNX graph; RTMPose RGB input, 256×256 affine crop with padding 1.25, SimCC split ratio 2.

## 5. Regression risks of the changes

- Side hysteresis delays a genuine side change by a few frames (by design), and a track started by a crop detection is undecided (0.5) until a full-frame detection arrives.
- Box-link can link two different hands whose boxes overlap by more than 50% for one frame (crossing hands). The predicted window is 0.15 s.
- All three changes are on only in the `recall`, `accurate` and `hybrid` presets; `baseline` reproduces the historical runs.

## 6. Reproduce

```sh
uv run python scripts/compare_baseline.py data/private/labels_v2/labels_v2_provisional.json dev recall=runs/<recall-run> hybrid=runs/<hybrid-run>
uv run python scripts/evaluate_identity.py data/private/labels_v2/labels_v2_provisional.json runs/<run>:dev
```
