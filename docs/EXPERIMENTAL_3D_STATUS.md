# 3D: what is real, what is assumed

| Representation | Source | Status |
| --- | --- | --- |
| 2D landmarks | MediaPipe (or RTMPose in the hybrid) | Model output |
| Hand-relative 3D | MediaPipe world landmarks | Model output, metres, origin at the hand |
| Fitted-from-2D 3D | `handfit`: 2D points + typical-hand depth (RTMPose-only hands) | `world_source: fitted_from_2d`, provenance `inferred` |
| Approx. camera-space 3D | PnP under an **assumed** equidistant fisheye (HFOV 150°) | Depth unvalidated; shown as "≈ m est." |
| Validated world / scene 3D | — | **Not available**: no depth, stereo, IMU or calibration in the footage ([DEPTH_FEASIBILITY](DEPTH_FEASIBILITY.md)) |
| Hand mesh | Joint-skinned procedural surface, bone-length calibrated per track | Visualisation, not a fitted model |
| MANO / WiLoR / HaMeR | — | **Not integrated:** needs the MANO licence (non-commercial, registration), multi-GB weights and in practice a GPU; download hosts are blocked from the cloud session. Integration path: a `mesh_*.npz` with `vertices_cam_m` and `faces` already loads in the viewer ("Add results") |

**Also not done:**
- **camera-motion compensation** (head motion is not removed);
- **monocular depth and SLAM** experiments.
