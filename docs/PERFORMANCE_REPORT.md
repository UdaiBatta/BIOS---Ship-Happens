# Performance report

## Where these numbers come from

- **Machine:** the cloud VM, Linux x86-64, 4 vCPU, 15 GB RAM, no GPU. They are **not** from the team laptop (RTX 4060 Laptop, Ryzen 7 7840HS, 16 GB, Windows 11). Run `scripts/benchmark_hybrid.py` there for the real figures.
- **Clip and interval:** `mytronlabs-000060-016.mp4`, dev 0–30 s, 900 frames at 1080p HEVC; inference at 960 px; 2 detection workers; `--no-video`.

## Definitions

| Term | Meaning |
| --- | --- |
| processing s | Process entry to exports written: decode, detection, tracking, exports. Excludes interpreter start-up, the quality pass, indexing and the proxy video (about 25 s more in the backend) |
| end-to-end FPS | frames ÷ processing s |
| detection wall s | Wall time of the parallel detection phase |
| detector CPU s | Sum of per-frame detector time across workers |
| p50 / p95 | Per-frame detector latency measured inside the workers. For `accurate`, the backward pass is reported separately |
| RSS | Sampled peak resident memory of the main process. Worker processes are not included |

## Results (dev 0–30 s)

| Preset | Processing s | End-to-end FPS | Detection wall s | Detector CPU s | p50 ms | p95 ms | Peak RSS MB (main) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `recall` | 46.5 | 19.3 | 36.6 | 49.2 | 54 | 80 | 199 |
| `accurate` (reverse-time pass +60.2 s) | 99.9 | 9.0 | 89.4 | 55.9 forward | 61 | 93 | 202 |
| `hybrid` (gated RTMPose fallback) | 115.2 | 7.8 | 105.5 | 159.5 | 169 | 370 | 204 |

- The `hybrid` p95 is dominated by frames that run RTMDet on four tiles plus RTMPose and the depth fit. Recovery only runs when fewer than two hands are found **and** a recently seen hand is missing.
- Tracking, smoothing and side logic take 0.27 s for 900 frames (`stage_seconds.track`), so they are negligible next to detection.

## Smoothing (One Euro, default `min_cutoff` 1.7, `beta` 0.03)

Measured on the `recall` dev run, wrist only:

| Measure | Raw | Smoothed |
| --- | ---: | ---: |
| Mean frame-to-frame jitter (\|2nd difference\|, image widths) | 0.0101 | 0.0040 |

- **Lag:** during fast motion (raw wrist > 0.5 widths/s, 202 samples), the smoothed wrist is on average 0.056 image widths from the raw one, about 3 frames. The synthetic test gives about 0.09 s at 0.6 widths/s.
- **Raw values are always exported** next to the smoothed ones (`image_xyz_raw`, `world_xyz_m_raw`). The filter resets after gaps over 0.2 s and never mixes tracks (`tests/test_motion_continuity.py`).

## GPU

- **MediaPipe Tasks (Python)** runs on the CPU here and on Windows: its GPU delegate is not available in the Windows Python package.
- **The RTM models** run with onnxruntime on the CPU. On the laptop, `onnxruntime-gpu` with the CUDA provider could take RTMDet/RTMPose off the CPU. This is untested and needs a matching CUDA/cuDNN install, so it was not changed before the deadline.
- **Peak VRAM** is therefore 0 for every preset as shipped.
