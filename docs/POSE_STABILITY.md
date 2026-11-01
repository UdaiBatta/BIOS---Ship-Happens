# Pose stability and score meanings

The presentation viewer uses wrist-centered hand posture by default. Its wrist placement is illustrative and fixed, so variation in the detector's hand-center origin no longer translates the entire displayed hand. Camera-space placement remains experimental.

Mesh and Mesh + skeleton now work with observed hand-relative joints, including frames whose camera lift was rejected. Generated surfaces use one bone-length profile per track and a bounded rendering cache. They remain procedural surfaces, not fitted hand-shape estimates. Predicted/lost hands do not acquire invented 3D meshes.

## Finger smoothing

The offline smoother separates finger-bone lengths from directions. Lengths are filtered independently. Each interior direction blends the current raw direction with a time-aligned interpolation of neighboring observed directions. This reduces isolated angular spikes without introducing a streaming delay into the completed replay. The filter uses future observations and is not a live estimator. It does not cross track boundaries or observation gaps.

Image landmarks retain the existing wrist RTS and finger-offset filter. Raw image and raw world landmarks are preserved. A corrected run must be processed again; changing the viewer alone does not rewrite old filtered exports.

## Measured temporal consistency

Two fresh accurate runs of the affected interval each contain 900 frames and 1,324 observed hand samples. Every raw image/world sample matches exactly between runs. The comparison covers 1,251 consecutive observed-hand triples and 20,016 finger-bone samples. The reference is the length-corrected smoother before centered direction filtering.

| Measure | Reference | Centered directions |
| --- | ---: | ---: |
| Unit-direction second difference, median | 0.0812 | 0.0671 |
| Unit-direction second difference, 90th percentile | 0.4378 | 0.2733 |
| Unit-direction second difference, 99th percentile | 1.3104 | 0.6499 |
| Joint distance from the same-frame raw estimate, 90th percentile | 14.27 mm | 14.58 mm |
| Joint distance from the same-frame raw estimate, 99th percentile | 24.82 mm | 27.46 mm |

The 90th-percentile angular-twitch metric fell by 37.56%. Joint-distance percentiles use 26,480 non-wrist joint samples. The increased extreme distance from raw is a tradeoff, not proof of better accuracy. Synthetic tests cover a single-frame spike, sustained bending, rapid rigid rotation, variable timestamps, gaps and preserved raw values.

An earlier cached-run probe covered 1,167 triples: 11 of 12 tracks with at least 20 triples improved at the 90th percentile, while one low-jitter track worsened from 0.075 to 0.090 over 27 triples. Results are therefore not uniformly better on every track.

Reproduce a same-raw comparison with `uv run python scripts/compare_pose_stability.py REFERENCE_RUN CANDIDATE_RUN`. The command rejects different raw observations and reports denominators and distance from raw alongside stability.

These measurements describe temporal stability, not landmark accuracy. The local machine-readable comparison and its methods are retained outside Git. Additional RTMPose comparisons on 5 local frames did not justify automatically replacing MediaPipe fingers.

## Confidence

**Side score** is classifier support for the displayed left/right label. For example, P(right) of 0.02 corresponds to left-side support of 0.98. It does not measure finger accuracy or the probability that the entire pose is correct.

**Landmark confidence remains uncalibrated.** No high confidence values are manufactured from smoothing or mesh appearance. Occlusion, wrong finger directions, and raw detector failures still require human review and labeled evaluation.
