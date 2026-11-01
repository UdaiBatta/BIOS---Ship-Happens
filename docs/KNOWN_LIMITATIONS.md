# Known limitations (31 Oct 2026)

**Evidence base**
- **One clip, provisional labels.** Every accuracy figure comes from one clip of one recording family, labelled by one annotator and not independently reviewed. Holdout is a later part of the same clip, not a different family.
- **The team's own clips are unlabelled.** The other families on the laptop (`mytronlabs-000003`, and others) have no labels, so their accuracy is unknown. About 50 labelled two-hand frames per family would allow measuring it.

**Detection**
- **Still hands are missed more.** Holdout 10/19 still samples vs 37/53 moving (`recall`). MediaPipe's palm detector keeps rejecting an unchanging view.
- **Bottom-edge and truncated hands.** Recall 7/23 on holdout with `recall`.
- **The hybrid recovers only hands that were recently tracked.** By design (the gate), it cannot find a hand that was never detected.
- **The hybrid loses precision** (dev 1.000 → 0.939) and costs about 3× detector time. Its benefit on other recording families is unmeasured.

**Landmarks and side**
- **Landmark accuracy is not measured.** Only 23 labelled hands carry landmarks, which is too few for a meaningful PCK. Landmarks over cloth are often visibly wrong.
- **Side is unknown or wrong for some hands.** About 1 in 10 matched holdout hands is still wrong. Tracks without full-frame evidence say `unknown`.
- **Same-side two-hand frames remain** (holdout 42% before the side fix). They may be a wrong side or another person's hand; this cannot be told apart without labels.

**3D and depth**
- **The 3D is not measured.** Camera-space 3D uses an assumed lens (HFOV 150°), and depth is unvalidated. The footage has no depth, stereo, IMU or intrinsics ([DEPTH_FEASIBILITY](DEPTH_FEASIBILITY.md)).
- **Fitted 3D for RTMPose-only hands** borrows a typical hand's depth (17.4 mm per-joint agreement with MediaPipe's own 3D on MediaPipe hands). It cannot see finger bending towards or away from the camera.
- **The mesh is a visual skin** of capsules around the lifted joints, not a fitted hand-shape model (MANO, WiLoR or HaMeR).

**Performance**
- **Measured on a 4-vCPU cloud VM, not the team laptop.** MediaPipe and RTM run on the CPU; GPU acceleration of the RTM models is untested.
- **No camera-motion compensation.** Head motion is not estimated; tracking relies on short-gap prediction and box overlap.
