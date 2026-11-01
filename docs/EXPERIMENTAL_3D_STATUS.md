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

## How the 3D panel shows depth

The reported problem: the hands in the 3D panel looked flat, had no sense of depth and gave no perspective beyond the video. The data was not the cause: the lifted hands have real thickness (the thinnest axis is a median 28% of the longest), and the wrists sit at 0.29–0.82 m (5th–95th percentile, median 0.51 m). The panel was the cause:

1. **Viewpoint.** The default view sat just behind and above the head camera, so it showed almost the same picture as the video. The default is now an angled **Side** view, where distance from the camera runs across the screen. **Top** and **Camera** (the head camera's own viewpoint, aimed at the hands) are one click away.
2. **Scale.** The view framed the whole 0.2–0.9 m working volume, so a hand covered a few pixels. **Follow hands** (on by default) centres the view on the hands' mean position over ±0.4 s and sizes it to the current frame. Mouse wheel zooms; double-click resets.
3. **Depth jitter.** The single-camera lift is noisy along the viewing axis. On the dev clip, the wrist depth changed by a median 3.1 cm between consecutive frames (90th percentile 10.5 cm), so the hand shook back and forth, and the "Smoothed" setting did nothing for 3D.
   - Camera-space 3D now goes through a forward-backward constant-velocity Kalman (Rauch–Tung–Striebel) smoother per track segment (gaps up to 0.2 s). It applies to the wrist (measurement noise 3 cm along depth, 0.6 cm sideways) and to the other joints relative to the wrist (0.4 cm).
   - Frame-to-frame depth change drops to a median 0.56 cm (90th percentile 2.0 cm). The smoothed wrist is a median 2.6 cm from the raw one.
   - The raw lift is kept and shown with **Raw**. This makes the motion steadier; it does not make the depth more accurate (the lens is still assumed).
4. **Depth cues.** Each hand now has:
   - a shadow on the bench plane;
   - a dashed drop line from the wrist to that plane;
   - a faint line of sight from the head camera.
5. **Frame and lighting.**
   - The camera frustum, which covered most of the view with a 150° lens, is drawn small and faint.
   - Mesh shading uses a fixed key light from above plus a weak fill from the viewer, instead of a light at the viewer's eye that hid the hand's shape.
   - Lines and triangles behind the viewer are clipped instead of being projected across the screen.
   - Wrist trails follow one track, so they no longer jump between hands.
