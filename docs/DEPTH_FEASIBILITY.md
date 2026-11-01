# Depth feasibility

## 1. What the footage contains

`ffprobe` of the official clip (`mytronlabs-000060-016.mp4`) shows:

- one HEVC video stream, 1920×1080, 30 fps;
- one AAC audio stream;
- container tags: creation time only.

There is **no depth stream, no stereo pair, no IMU or GPMF track, and no lens intrinsics or distortion**. The project therefore has **RGB only**. Nothing in this project is RGB-D, and no output may be described as measured depth.

Current camera-space 3D (`lift.py`) comes from PnP of MediaPipe's hand-relative 3D under an **assumed** equidistant fisheye lens (HFOV 150°, principal point at the centre). Its depth scales with the assumed focal length and with MediaPipe's learned hand size. It is labelled "ASSUMED (not calibrated) · depth unvalidated" in the files and in the viewer.

## 2. The reference project (Reddit comment)

Their setup:
- an RGB-D camera on a Jetson TX2, with no tracker, to save time per frame;
- depth as an extra detector input, which improved body-part classification mAP;
- measured depth back-projected with the camera intrinsics, `X = (u − cx)·Z/fx`, `Y = (v − cy)·Z/fy`, `Z = depth`, giving 3D points, a scene point cloud and distances between body parts.

That works because **Z is measured** and the camera is calibrated. Their mAP gain is their result on their data. It has not been tested here and must not be quoted as ours.

## 3. Options for this project, best first

| Option | Gives | Needs | Status |
| --- | --- | --- | --- |
| Record with a head-mounted RGB-D camera (RealSense D405/D435, ZED, Azure Kinect) | Measured depth per landmark (sample a small window, median), real intrinsics, hand-to-object distances | Hardware, new recordings, depth–RGB alignment | Not available for the official footage |
| Calibrate the fisheye on a consented recording, or get the organisers' intrinsics | Removes the HFOV assumption from the current lift | A checkerboard video or organiser data | Open ([TODO](TODO.md) items 10–11) |
| Monocular depth network (e.g. Depth Anything V2 Small, Apache-2.0) | Relative depth per pixel. The hand can fix its scale: PnP hand depth acts as a ruler. Could also confirm hand candidates as the nearest object | Model weights (both download hosts are blocked from the cloud session; they can be uploaded like the RTM models), CPU/GPU time, testing on fisheye images | **Not tested** |
| Structure from motion / SLAM (COLMAP, ORB-SLAM3 with fisheye) | Camera path plus a sparse map, so hands can sit in a fixed scene frame | Lens model; hours of tuning | Not started; after hand identity is stable |

## 4. How a monocular depth test would be judged

Before integrating anything, it must beat RGB-only on the same labelled frames. Planned checks:
1. Use depth as a filter for hybrid candidates: reject a recovered hand that is not nearer than the surrounding surface. Measure precision and recall against the gated hybrid.
2. Check its depth at the lifted wrists against PnP depth: rank correlation and stability between frames.
3. Measure runtime per frame on the team laptop.

If it does not improve precision or identity on dev, it is not integrated. Depth does not decide left/right.
