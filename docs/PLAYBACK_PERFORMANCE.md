# Playback performance

**How frames reach the browser:** one H.264 proxy MP4 per run (frame-exact; HTTP Range), played by a hidden `<video>`. Each redraw copies the current video frame into a canvas and draws the 2D skeleton, the 3D panel, the timeline and the signals on canvases. There is no frame-by-frame image fetching and no inference during playback.

**Measured** in headless Chromium on the cloud VM (no GPU, software rendering), playing a 10 s hybrid run with meshes for 6 s:

| | Before | After |
| --- | --- | --- |
| Overlay landmark frame ≠ presented video frame | **173 / 179** | **0 / 180** (also 0/90 at 0.5×; matches after seek and pause) |
| Video frames presented per s | 29.9 | 29.5–30 |
| Dropped video frames | 0 | 0–2 (with the 1,872-triangle mesh; see below) |
| Redraws per 6 s | 349 (every display refresh) | 193 (once per presented frame) |
| JS heap growth | 0 MB | 0 MB |

**Root cause of the stutter:** the overlays used `video.currentTime`, which runs ahead of the frame on screen, so the skeleton jumped between frames out of step with the image. **Fix:** one clock, `requestVideoFrameCallback` media time, for video, 2D, 3D, timeline and details. Redraws now happen only when the presented frame changes.

**Remaining cost:** copying each video frame into the canvas (`drawImage`) takes 5–8 ms per redraw with software rendering. Mesh drawing is 1.6 ms (p95 5 ms), the timeline 0.4 ms and the signals 0.2 ms. The 1–2 dropped frames per 6 s are attributed to the software copy. **Not measured on the RTX 4060 laptop**: run `scripts/benchmark_hybrid.py` there and watch playback.
