# Mesh animation validation

| Check | Result |
| --- | --- |
| Outward winding, every part, 80 real and mirrored (left/right) hands | 80/80 |
| Fingertip-bone length across 15 noisy frames | raw varies; calibrated constant (sd < 1e-9) |
| Bone directions after calibration | unchanged (cosine > 0.999) |
| Meshes only for observed or reacquired hands | yes; predicted and lost hands keep a 2D skeleton or nothing |
| RTMPose-only hands | mesh drawn from **fitted-from-2D** 3D, labelled so; never counted as observed 3D |
| Hands lifted on a 10 s hybrid run | MediaPipe 209/209, fitted-from-2D 28/39 (11 rejected as degenerate) |
| Draw time for 2 meshes | 1.6 ms mean, 5 ms p95 (software rendering) |

**Not validated:** shape accuracy against a real hand (no 3D ground truth) and depth (assumed lens).
