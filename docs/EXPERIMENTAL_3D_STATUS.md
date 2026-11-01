# 3D: what is real, what is assumed

| Representation | Source | Status |
| --- | --- | --- |
| 2D landmarks | MediaPipe (or RTMPose in the hybrid) | Model output |
| Hand-relative 3D | MediaPipe world landmarks | Model output, metres, origin at the hand |
| Fitted-from-2D 3D | `handfit`: 2D points + typical-hand depth (RTMPose-only hands) | `world_source: fitted_from_2d`, provenance `inferred` |
| Approx. camera-space 3D | PnP under an **assumed** equidistant fisheye (HFOV 150°) | Depth unvalidated; shown as "≈ m est." |
| Validated world / scene 3D | — | **Not available**: no depth, stereo, IMU or calibration in the footage ([DEPTH_FEASIBILITY](DEPTH_FEASIBILITY.md)) |
| Generated hand surface | Joint-skinned procedural surface, bone-length calibrated per track | Viewer visualization, not a fitted model; 970 vertices and 1,872 triangles |
| MANO / WiLoR / HaMeR fitting | — | **Not integrated:** no fitted-model inference path is shipped. The viewer can load externally produced mesh files through **Add results**. |

The viewer defaults to wrist-centered **Hand posture**. Selecting experimental camera space uses a posture fallback when that frame has no accepted camera joints. Mesh surfaces can be generated from those observed hand-relative joints too. The fallback carries no camera depth or placement and does not change camera acceptance masks. See [POSE_STABILITY](POSE_STABILITY.md).

**Also not done:**
- **camera-space smoothing**: the lift uses raw landmarks; the Raw/Smoothed toggle changes image and hand-relative coordinates, while the camera-space lift remains raw;
- **camera-motion compensation** (head motion is not removed);
- **monocular depth and SLAM** experiments.
