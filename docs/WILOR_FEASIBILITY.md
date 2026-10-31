# WiLoR feasibility gate — 31 October 2026

**Decision:** preserve the working CPU skeleton pipeline; benchmark meshes separately before promising integration. No WiLoR checkpoint has been run and no mesh performance result is claimed.

## Verified environment and upstream requirements

The development host is an Apple M1 MacBook Air with 8 GB unified memory, macOS 26.6.2. It is not the assumed Windows/RTX 4060 laptop. MediaPipe runs through its CPU delegate in this project. A separate RTX machine remains unverified.

The [official WiLoR README](https://github.com/rolpotamias/WiLoR) documents an environment tested with Python 3.10, PyTorch 2.0.0 and CUDA 11.7. It requires a hand-detector checkpoint, `wilor_final.ckpt`, and a separately acquired `MANO_RIGHT.pkl`. The March 2026 `--fast` option uses half precision and model pruning; its published speed claim is not a measurement on this host. Do not assume CPU/MPS compatibility or transfer the reported speedup to the baseline.

The upstream [requirements](https://github.com/rolpotamias/WiLoR/blob/main/requirements.txt) include PyTorch Lightning, pyrender, smplx, a Git-sourced chumpy, and ultralytics 8.1.34. This is a separate dependency stack; installing it into the baseline environment risks wasting the working milestone.

The upstream [license file](https://github.com/rolpotamias/WiLoR/blob/main/license.txt) identifies CC BY-NC-ND 4.0. [MANO](https://mano.is.tue.mpg.de/) has its own acquisition/license requirements. Keep upstream code and model assets outside the public baseline repository and check the actual intended distribution/use against those terms before integration. Do not describe this stack as unrestricted commercial software.

The official README links [WiLoR-mini](https://github.com/warmshao/WiLoR-mini) as a simplified demo implementation. It has not been installed, its equivalence has not been established, and it is not a verified replacement in this project.

## Benchmark before integration

1. Verify access to actual GPU hardware, CUDA/PyTorch compatibility and authorized MANO assets. If these are absent by the mesh milestone, keep the skeleton fallback and concentrate on evaluation.
2. Use an isolated checkout/environment, batch size 1, fixed 20–50-frame sample covering both hands, blur, gloves and occlusion. Preserve the same source timestamps as the baseline.
3. Measure installation time, load time, total inference time, peak GPU memory, successful mesh coverage and visible shape/handedness failures. Record checkpoint hashes and configuration. Never score hidden/predicted geometry as observed.
4. Inspect meshes against source pixels, including left-hand reflection and camera convention. Metric hand shape does not establish accurate root translation.
5. Only after this passes, add an optional mesh result keyed by `(frame_index, track_id)` and a Rerun Mesh3D path. Missing meshes must fall back to the observed skeleton. Do not fabricate a mesh adapter before real output formats have been inspected.

Stop unreliable mesh work by hour 12. SLAM remains a separate optional gate; it cannot supply hand depth automatically.
