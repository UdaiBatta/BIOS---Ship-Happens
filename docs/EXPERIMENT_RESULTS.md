# Experiment results: baseline vs hybrid (31 Oct 2026)

**Data and protocol**
- One clip (`mytronlabs-000060-016`), provisional labels.
- Dev 0–30 s (72 labelled hands); holdout 60–150 s (78 labelled hands).
- Every choice was made on dev. The holdout was run once per final configuration.
- Matching is one-to-one: raw observed wrist within 0.10 image diagonals. Predicted or interpolated hands never count.
- Times are from a 4-vCPU cloud VM with 2 workers (see [PERFORMANCE_REPORT](PERFORMANCE_REPORT.md)).

**Go/no-go rule, fixed before testing:** at least +5 points of recall for at most −2 points of precision, no more identity switches, and runtime acceptable offline.

## Detection

| Version | Configuration | Dev recall | Dev precision | Holdout recall | Holdout precision | Holdout F1 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| B0 | `baseline` (MediaPipe defaults) | 17/72 | 17/17 | 19/78 | 19/19 | 0.39 |
| B1 | `recall`: thresholds 0.3 + centre crop | 36/72 | 1.000 | 39/78 | 0.975 | 0.661 |
| — | `accurate`: B1 + reverse-time pass | 41/72 | 1.000 | **46/78** | **0.958** | **0.730** |
| B2 | RTMDet boxes (2×2 tiles, ≥ 0.2) | box at 43/72 labelled hands; at 20 of the 36 B1 misses | — | — | — | — |
| B3 | B1 + MediaPipe retry in RTMDet boxes | 0 of 20 boxed misses read (threshold 0.3) | 4 false | — | — | — |
| B4a | B1 + B3 + RTMPose fallback, wide gate | 46/72 | 0.868 | — | — | — |
| B4b | B1 + RTMPose fallback (B3 off), wide gate | 46/72 | 0.939 | 46/78 | 0.902 | 0.713 |
| B4c / B5 | B4b with the tracker's gate + recovery link (**final `hybrid`**) | 45/72 | 0.938 | **47/78** | 0.887 | 0.718 |
| B6 | smoothing (all presets; does not change detection) | = | = | = | = | = |
| B7 | depth-assisted | not run: no depth in the data, model not available ([DEPTH_FEASIBILITY](DEPTH_FEASIBILITY.md)) | | | | |

**Per category on holdout (`recall` → final `hybrid`).** Tags overlap.

| Tag | `recall` | `hybrid` |
| --- | ---: | ---: |
| holding an object | 15/36 | 16/36 |
| side view | 12/30 | 13/30 |
| image edge | 7/23 | 9/23 |
| cloth | 9/14 | 10/14 |
| fist | 2/6 | 5/6 |
| back of hand | 12/15 | 13/15 |
| fully visible | 27/46 | 33/46 |

**Decisions**
- **`hybrid`: no-go as a default.** It gives +10 points of recall, but precision drops 8.8 points (6 false detections, against 1). It is also 2.6× slower than `recall`. It stays an opt-in experimental accuracy mode.
- **`accurate` is the better accuracy mode on this clip:** about the same recall, higher precision and F1, and about 2× the time of `recall`.
- **`recall` stays the default.**
- `hybrid` combined with the reverse-time pass was not tested.

## Identity (tracking replayed on the same detections; holdout once)

| | Before (all presets) | After (`recall`) |
| --- | --- | --- |
| Wrong side, matched holdout hands | 11/49 | **5/49** (12 unknown) |
| Labelled Left↔Right flips, holdout | 8 | **2** |
| Left↔Right changes within tracks, holdout run | 29 | **3** |
| Ghost frames (predicted skeleton on an observed hand), holdout | 10 | 6 |
| Hybrid tracks created, holdout | 71 (wide gate) | 59 (tracker gate + recovery link) |
| Schema-invalid frames, hybrid holdout | 9 | **0** |

Full tables and the variants that were rejected: [HANDEDNESS_ROOT_CAUSE](HANDEDNESS_ROOT_CAUSE.md).

## Motion (One Euro, wrist)

| Run | Raw jitter | Smoothed jitter | Fast-motion smoothed − raw |
| --- | ---: | ---: | ---: |
| `recall`, dev | 0.0101 | 0.0040 | 0.056 widths (~3 frames) |
| `recall`, holdout | 0.0096 | 0.0031 | — |

## Not measured

- **Landmark PCK:** too few landmark labels.
- **3D error:** no ground truth.
- **Laptop runtime:** run `scripts/benchmark_hybrid.py`.
- **GPU VRAM:** all models run on the CPU.
- **The team's other recording families:** no labels.

## Reproduce

```sh
uv run egohand process data/private/mytronlabs-000060-016.mp4 --out runs/X --duration 30 --preset recall --workers 2 --no-video
uv run python scripts/compare_baseline.py data/private/labels_v2/labels_v2_provisional.json dev recall=runs/X hybrid=runs/Y
```
