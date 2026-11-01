# Known limitations (1 Nov 2026)

**Evidence base**
- **Current-session common accuracy is not measured.** The local `labels_v2` inputs needed to rescore the prior experiments are missing. Earlier figures in this document and [RESULTS_V2](RESULTS_V2.md) are historical and provisional, from one clip and one annotator; they have not been independently reviewed.
- **Generalization is unmeasured.** The current local video collection includes multiple clips, but there is no current labeled evaluation across recording families. Processing availability does not establish accuracy.

**Detection (historical findings, not current-session scores)**
- **Still hands are missed more.** Holdout 10/19 still samples vs 37/53 moving (`recall`). MediaPipe's palm detector keeps rejecting an unchanging view.
- **Bottom-edge and truncated hands.** Recall 7/23 on holdout with `recall`.
- **The hybrid recovers only hands that were recently tracked.** By design (the gate), it cannot find a hand that was never detected.
- **The hybrid loses precision** (dev 1.000 → 0.939) and costs about 3× detector time. Its benefit on other recording families is unmeasured.

**Landmarks and side (historical findings, not current-session scores)**
- **Landmark accuracy is not measured.** Only 23 labelled hands carry landmarks, which is too few for a meaningful PCK. Landmarks over cloth are often visibly wrong.
- **Side is unknown or wrong for some hands.** About 1 in 10 matched holdout hands is still wrong. Tracks without full-frame evidence say `unknown`.
- **Same-side two-hand frames remain** (holdout 42% before the side fix). They may be a wrong side or another person's hand; this cannot be told apart without labels.

**3D and depth**
- **The 3D is not measured.** Camera-space 3D uses an assumed lens (HFOV 150°), and depth is unvalidated. The footage has no depth, stereo, IMU or intrinsics ([DEPTH_FEASIBILITY](DEPTH_FEASIBILITY.md)).
- **Fitted 3D for RTMPose-only hands** borrows a typical hand's depth (17.4 mm per-joint agreement with MediaPipe's own 3D on MediaPipe hands). It cannot see finger bending towards or away from the camera.
- **The generated mesh is a visualization** built from lifted joints, with bone-length calibration. It is not a fitted hand-shape model (MANO, WiLoR or HaMeR).

**Events and privacy**
- Motion events are inferred from tracking evidence. Their thresholds have not been validated against labeled event intervals, and head motion can look like hand motion.
- Privacy scanning covers faces only and is experimental review assistance. It can miss faces and flag non-faces; it is not a privacy certification. Screens and text are not scanned.

**Performance**
- The timing tables in [PERFORMANCE_REPORT](PERFORMANCE_REPORT.md) are historical cloud-VM measurements, not current-session or team-laptop measurements. MediaPipe and RTM CPU/GPU behavior should be benchmarked in the target environment.
- **No camera-motion compensation.** Head motion is not estimated; tracking relies on short-gap prediction and box overlap.
