# Measured results v2 — detection, identity, quality layer, efficiency, geometry

Everything here was measured on **one clip** (`mytronlabs-000060-016.mp4`, 1920×1080 HEVC, 30 FPS, 180 s), in **one recording family** (`mytronlabs-000060`), on a **Linux x86_64 cloud VM with 4 vCPUs and 16 GB RAM**, using MediaPipe 0.10.35 on CPU. The 2D labels are **provisional**: one annotator in the coding session read them visually from grid overlays, without viewing predictions, and **no person has independently reviewed them**. The label file records this, and every evaluator output from it is stamped `label_status: provisional`. Treat every accuracy figure below as provisional until a team member reviews the labels.

## 1. Label set and protocol

| Split | Source intervals | Frames | Labeled hands | full / occluded / truncated | wearer_left / wearer_right / unknown |
| --- | --- | ---: | ---: | --- | --- |
| dev | 0–12 s (every 12th frame), 12–30 s (every 45th) | 42 | 72 | 33 / 29 / 10 | 33 / 34 / 5 |
| holdout | 60–72, 87–99, 138–150 s (every 20th frame) | 54 | 78 | 46 / 9 / 23 | 42 / 34 / 2 |

- A hand is labelable when some of the palm or back of the hand is visible. Fingertip-only views and distant background hands under about 40 px are excluded.
- Wrists outside the frame are allowed only with `wrist_in_frame=false`.
- The holdout is **temporal, from the same clip and family**. It is not a cross-family test.
- Splits are contiguous intervals, so adjacent frames never cross the split.
- Matching uses raw observed wrists only. Predicted tracks never count as detections. The gate is 0.10 image diagonals.
- Gate audit: matched wrists sit at a median of 0.012–0.013 diagonals (maximum 0.047), and a 0.05 gate gives identical counts in every reported configuration. The 0.10 gate is not inflating matches.
- Wilson 95% intervals assume independent samples. Frames from one clip are correlated, so real uncertainty is larger.

## 2. Detection bake-off on dev (0–30 s, 900 frames)

All rows use persistent tracking and smoothing with `--no-video`; only the detector settings differ. Runs went two at a time, so the FPS columns are contended (see §6 for controlled timing). Rescue crops run only when fewer than two hands are found.

| Config | Recall | Precision (labeled frames) | full / occl / trunc | Frames with an observed hand | Detector FPS |
| --- | ---: | ---: | --- | ---: | ---: |
| B0 (default) | 17/72 = 0.24 | 17/17 | 9/33, 7/29, 1/10 | 164/900 | 36 |
| B0, thresholds 0.3 | 22/72 = 0.31 | 22/22 | 15/33, 6/29, 1/10 | 229/900 | 34 |
| Historical center crop (960 px frame) | 28/72 = 0.39 | 28/28 | 12/33, 13/29, 3/10 | 350/900 | 18 |
| Full-resolution center crop | 22/72 = 0.31 | 22/22 | 9/33, 12/29, 1/10 | 300/900 | 16 |
| Full-resolution center crop, area-downscaled to 480 | 28/72 = 0.39 | 28/28 | identical to the historical crop | 350/900 | 15 |
| Tiles ×3, full resolution | 25/72 = 0.35 | 25/25 | 12/33, 12/29, 1/10 | 349/900 | 8 |
| Tiles ×3, area-downscaled to 480 | 33/72 = 0.46 | 33/33 | 16/33, 15/29, 2/10 | 401/900 | 8 |
| Track-guided crops | 17/72 = 0.24 | 17/17 | same as B0 | 173/900 | 26 |
| Guided + tiles (480) | 33/72 = 0.46 | 33/33 | 16/33, 15/29, 2/10 | 392/900 | 7 |
| **0.3 + historical center crop (chosen)** | **36/72 = 0.50** | **36/36** | 17/33, 14/29, 5/10 | 441/900 | 17 |
| 0.3 + guided + tiles (480) | 34/72 = 0.47 | 34/34 | 17/33, 13/29, 4/10 | 464/900 | 7 |

Findings:

1. **Full-resolution crops alone did not help.** They were worse than crops cut from the 960 px frame (22 vs 28). With area-filtered downscaling to 480 px the result matches the historical crop exactly, so the difference is input resampling, not available resolution. The plan's assumption that full resolution is better is rejected for this footage.
2. **Track-guided crops added almost nothing** (11 of 376 crops accepted). Their stop rule works, as tested: no self-confirmation beyond 1 s.
3. **Choice, made on dev only:** thresholds 0.3 plus the historical center crop. It gives the best recall at about half the detector FPS of B0. Tiles cost twice as much again for lower recall.
4. **Precision check outside labeled frames.** In 12–30 s, where hands are mostly out of view, the chosen configuration observes hands in 172 frames vs 33 for B0. A prediction-assisted audit of 8 evenly sampled such frames found 8/8 on real wearer hands, one with landmarks partly offset. This is a small sample and not a precision estimate.

## 3. Holdout (run once, after the dev choice)

| Config | Recall (Wilson 95%) | Precision (Wilson 95%) | full / occl / trunc | Frames with an observed hand (60–150 s) |
| --- | --- | --- | --- | ---: |
| B0 (default) | 19/78 = 0.24 [0.16, 0.35] | 19/19 [0.83, 1.00] | 15/46, 4/9, 0/23 | 534/2700 |
| B0, thresholds 0.3 | 29/78 = 0.37 | 29/30 | 24/46, 4/9, 1/23 | 782/2700 |
| Historical center crop | 24/78 = 0.31 | 24/24 | 16/46, 5/9, 3/23 | 807/2700 |
| **0.3 + historical center crop** | **39/78 = 0.50 [0.39, 0.61]** | **39/40 [0.87, 1.00]** | 27/46, 5/9, 7/23 | 1081/2700 |

- **Recall** rises from 0.24 to 0.50 (+26 points) on holdout, consistent with dev (+26). The single false positive is at frame 2810, near the wearer's forearm.
- **Remaining holdout misses**, by tag (a hand can carry several): holding an object 21, side view 18, image edge 16, cloth 5, fist 4. Truncated hands at the bottom edge remain the weakest category: 7/23 recovered.
- **Default not switched.** The CLI default is still B0, so historical results stay reproducible. Use the chosen configuration explicitly: `--rescue-crop --detection-threshold .3 --presence-threshold .3 --tracking-threshold .3`. Switch the default once the labels are reviewed.

## 4. Left/right and identity (matched wearer hands only)

| Split / config | Raw per-frame side correct | Online smoothed side | Offline whole-track vote (unknown allowed) | ID changes between consecutive labeled samples |
| --- | ---: | ---: | --- | ---: |
| dev B0 | 14/17 | 15/17 | 16/17 | 4/13 |
| dev chosen | 25/33 | 27/33 | 27/33 correct, 5 unknown, 1 wrong | 12/32 |
| holdout B0 | 19/19 | 19/19 | 18/19 correct, 1 unknown | 3/14 |
| holdout chosen | 32/38 | 33/38 | 30/38 correct, 3 unknown, 5 wrong | 7/33 |

- **Convention check.** MediaPipe's handedness matches the wearer's side *without* mirroring: 25 correct vs 8 mirrored on dev. The current convention is confirmed for this camera, and no global flip is needed.
- **Recovered hands carry less reliable side.** Hands recovered by the crop and lower thresholds are harder: side accuracy drops from 100% to 84% on holdout, and the extra tracks fragment more.
- **The offline vote is not a clear win.** It turns some errors into `unknown` but also propagates wrong associations. It stays an optional view, not the default.
- **Aspect-correct tracker distances** (`--tracker-units diagonal`) changed nothing for B0 and reduced dev ID changes from 12 to 9 for the chosen configuration, but lowered vote accuracy. The evidence is inconclusive, so the default is unchanged.
- **ID changes** are sampled at sparse labeled frames, often 0.4–0.7 s apart. They are not full-sequence switch counts.

## 4b. Why is a hand missing? (`missing_reason`, schema 0.3)

Chosen configuration, re-run with the new field. Observations are identical to the §2/§3 runs: 441/441 dev frames, zero coordinate difference.

| Split | Non-observed track samples: out_of_view / unknown (whole run) | `out_of_view` claims in labeled frames contradicted by a nearby undetected labeled hand (within 0.15 diag of the last wrist) | `unknown` records in labeled frames with a nearby undetected labeled hand |
| --- | --- | ---: | ---: |
| dev (0–30 s) | 167 / 608 | 2 / 4 | 25 / 38 |
| holdout (60–150 s) | 823 / 981 | 6 / 15 | 21 / 23 |

- **Read `out_of_view` as a hint.** It is wrong about 40% of the time on holdout, typically for hands gripping the slab at the bottom edge.
- **Most `unknown` gaps are detector misses.** In labeled frames, the hand is usually still visible nearby: 21/23 on holdout. A "lost" track does not mean the hand is gone.
- **The rule was not retuned.** Only the holdout shows the problem clearly, so retuning it would leak holdout evidence into the design.

## 4c. Continuity and capture conditions (schema 0.5 runs, provisional labels)

| Split / config | Labeled hands with matches | Mean (max) track IDs per labeled hand | Tracks | Bridged gaps n, median, max | Longest predicted run |
| --- | ---: | --- | ---: | --- | ---: |
| dev, B0 | 4 | 2.00 (3) | 12 | 28, 0.10 s, 0.73 s | 0.133 s |
| dev, chosen | 4 | 4.00 (8) | 22 | 65, 0.07 s, 0.63 s | 0.133 s |
| holdout, B0 | 5 | 1.60 (3) | 26 | 40, 0.15 s, 0.73 s | 0.133 s |
| holdout, chosen | 6 | 2.17 (3) | 44 | 135, 0.13 s, 0.80 s | 0.133 s |

- **Predicted runs stay under the 0.15 s 2D-only cap.** Bridged gaps reach the 0.8 s retention limit.
- **The recovery setting trades continuity for recall.** It produces more tracks and more fragments per labeled hand.
- **"Tracks ending unobserved" adds nothing:** every track ends that way, because all tracks eventually retire.

Recall by capture condition. The conditions are a provisional single-annotator `conditions.json`; nothing was excluded.

| Split / config | lighting ok | lighting harsh | occlusion none | occlusion partial |
| --- | ---: | ---: | ---: | ---: |
| dev, B0 | 15/60 | 2/12 | 2/12 | 15/60 |
| dev, chosen | 30/60 | 6/12 | 6/12 | 30/60 |
| holdout, B0 | 14/47 | 5/31 | 10/50 | 9/28 |
| holdout, chosen | 25/47 | 14/31 | 22/50 | 17/28 |

**These slices are confounded with activity.** On dev, "harsh lighting" and "no occlusion" are both the 12–30 s walking interval, where hands are mostly cut off at the image edge. With one clip, lighting or occlusion effects cannot be separated from the task, so do not read these as causal effects.

## 5. Quality layer (heuristic; thresholds set on the dev interval)

`motioniq quality` produces per-frame signals, 1 s windows (*suitable / needs_review / insufficient_evidence*) and a ranked queue. To check it against the labels, each labeled frame is classified using the same matching as above:

- **missed:** at least one labeled hand not detected;
- **all matched:** labeled hands present and all detected;
- **no visible hand.**

| Split / run | Missed-hand frames in flagged windows | Fully detected frames kept *suitable* | Fully detected frames flagged *needs_review* | *Insufficient evidence* frames that had a visible hand | Seconds suitable / needs review / insufficient | Review items per minute |
| --- | ---: | ---: | ---: | ---: | --- | ---: |
| dev, B0 | 33/36 | 2/2 | 0/2 | 5/9 | 2 / 15 / 13 | 10.0 |
| dev, chosen | 21/26 | 5/12 | 7/12 | 0/3 | 6 / 20 / 4 | 12.0 |
| holdout, B0 | 31/43 | 2/2 | 0/2 | 12/18 | 10 / 32 / 48 | 12.7 |
| holdout, chosen | 22/35 | 4/10 | 6/10 | 0/3 | 17 / 52 / 21 | 12.0 |

Interpretation:

- **What flagged windows mean.** On holdout, 63% of frames with a missed hand fall in flagged windows (81% on dev). The flags help direct review but do not reliably find every miss.
- **What "insufficient evidence" means.** It means no hand was observed, not that no hand was visible: 12 of 18 such labeled frames under B0 had a visible hand. The queue says so explicitly.
- **False-alarm burden.** About 12 review items per minute of footage, and more than half of the processed time is *needs review* in this hard clip. That is too many for unattended triage; it is a starting point for focused review. Some fully detected frames are flagged because the *other* hand in the same window flickers. This is window-level evidence, not a frame-level error, but it still costs review time.
- **Not measured:** whether a flagged interval is truly problematic for a downstream task, review-time savings, and any downstream training benefit.
- **Global image signals are weak here.** The Laplacian blur metric is dominated by the granite texture; the relative blur ratio fired in 3 dev windows. These signals cannot confirm blur or occlusion on the hand itself.

## 6. Efficiency

### Timestamp probing
The original pipeline used an FFprobe frame query, which decodes **every frame of the source file**. On this host that took **79 s** for the 180 s clip, even when processing only 30 s. Sorted packet PTS take **0.17 s**. On this file they match all 5,400 decoded timestamps exactly: DTS equals PTS, so there are no reordered frames. The runtime path verifies 48 decoded frames plus the frame count, takes about 1.5 s in total, and falls back to the full probe on any mismatch.

### Controlled timing
Measured on the same 4-vCPU VM, sequentially with no other load. Each run covers the same 30 s interval (900 frames) and writes all outputs: 1600×900 H.264 preview, Rerun recording, JSONL/CSV/NPZ. Each configuration ran twice; ranges show both runs. Python start-up is excluded.

| Config | Total processing | End-to-end FPS | Detector FPS | Detector p95 | Peak RSS (sampled) | Frames with an observed hand |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| B0 with the old full-decode timestamp probe | 129.3–129.5 s | 6.95–6.96 | 37.6 | 43–44 ms | 458–461 MB | 164 |
| B0 with the verified packet probe | 55.0–58.6 s | 15.4–16.4 | 37.0–38.6 | 41–44 ms | 457–462 MB | 164 |
| Chosen (0.3 + center crop), packet probe | 84.6–87.2 s | 10.3–10.6 | 18.1–18.7 | 80–81 ms | 541–542 MB | 441 |
| Quality pass on the cached chosen run | 8.3–8.4 s | ≈108 frames/s | — | — | ≈150 MB | — |

Stage breakdown, B0 with the packet probe (seconds): probe 1.1, setup 1.0, decode 2.8–2.9, resize/convert 0.9–1.0, **detection 23.3–24.3**, tracking 0.1, export rows 0.3, **preview rendering and encoding 19.8–21.7**, Rerun logging 5.5–5.8, finalize 0.2.

- The probe change makes complete processing **2.3× faster** with identical observations: 164/164 frames, identical raw coordinates against the earlier run.
- After detection, preview rendering is the largest cost. A batch job that only needs data can use `--no-video` and render previews only for intervals that need review.
- The quality layer reruns from cache at about 3.6× real time for this clip, without new inference.
- **Scale:** these are single-clip measurements on one VM. A per-clip batch design (one CPU worker per clip, observations cached once, quality and exports recomputed from the cache) is plausible, but its throughput, failure handling and storage costs are **untested**. Nothing here demonstrates processing at the 100 TB scale mentioned by the organizer.

## 7. Experimental camera-space lift (assumed lens)

`motioniq lift` on the dev B0 run (193 observed hands, 188 lifted, 5 rejected for reprojection RMSE above 25 px):

| Assumed horizontal FOV | Median wrist depth | p5–p95 | Wrist depth in 0.2–0.9 m | Reprojection RMSE (median) | PnP rotation from identity (median) |
| ---: | ---: | --- | ---: | ---: | ---: |
| 120° | 0.64 m | 0.42–0.94 m | 91% | 6.6 px | 30° |
| 150° | 0.50 m | 0.30–0.70 m | 99% | 6.7 px | 34° |
| 180° | 0.41 m | 0.22–0.53 m | 98% | 6.9 px | 39° |

- **Depth depends on the assumed lens**, and the reprojection residual cannot discriminate between lenses: it is almost the same at every FOV.
- **MediaPipe's hand-relative axes are not camera-aligned here** (median rotation 30–39°), so a translation-only lift would be wrong.
- **MediaPipe's hand scale varies:** raw bone-length coefficient of variation per track has a median of 0.15 and p90 of 0.30. Scale is unstable, and that feeds directly into depth.
- **Inter-hand center distance:** median about 0.41 m over the 27 frames where both hands were lifted. **Unvalidated.**

Conclusion: keep hand-relative 3D as the reported result. Camera space is an experimental view labeled "assumed lens, depth unvalidated". The calibrated own-recording test from the plan has not been done.

## 7b. Latency and accuracy round 2 (backend work, dev split only)

**Parallel chunked detection** (`--workers N`, recall preset, 30 s, no preview, 4 vCPU, runs one at a time):

| Workers | Processing | Detections vs sequential |
| ---: | ---: | --- |
| 1 | 63.2 s | — |
| 2 | 50.4 s | identical (0/900 frames differ) |
| 3 | 46.0 s | 12 frames differ by ≤ 0.0015 normalized; one seam did not converge within 60 lookahead frames (reported in `metrics.parallel.seams`) |
| 4 | 48.9 s | identical |

Without seam repair, 3 workers differed on 72 frames. The backend defaults to 2 workers on hosts with 4 or more CPUs.

**Cheap accuracy variants** on top of the recall preset (dev, provisional labels; reference 36/72 recall, 36/36 precision, 4.0 track IDs per labeled hand):

| Variant | Recall | Precision | Notes | Decision |
| --- | ---: | ---: | --- | --- |
| thresholds 0.25 | 36/72 | 36/36 | more frames with detections, no recall gain | rejected |
| thresholds 0.20 | 36/72 | 36/37 | one false positive | rejected |
| primary input 1280 px | 28/72 | 28/28 | worse | rejected |
| retain tracks 1.5 s | 36/72 | 36/36 | fragments 4.0 → 3.25, ID changes 12 → 9, but whole-track side vote 27 → 22 correct (likely wrong joins) | not adopted |
| + bottom-padded crop (lower half, black padding below the frame, area-downscaled to 480) | 37/72 | 37/37 | truncated hands unchanged (5/10); processing 52 → 74 s | rejected: +1 hand is within noise for +42% time |
| + bottom-padded crop at full resolution | 33/72 | 33/33 | worse | rejected |

None of these was run on holdout, because none passed on dev. The recall preset stays the default for the backend. The remaining misses (side views, hands gripping objects, hands cut off at the bottom edge) look like limits of MediaPipe's palm detector. The next accuracy levers are a dedicated hand detector (licence-gated; see TODO) and reviewed labels from more recording families.

## 8. Reproduction

The final demo run (`runs/final_demo`, private) was produced by the same commands with `--preset recall --rrd --governance`. Its 900 frames validate against the frame schema, and its observations are identical to the chosen-configuration runs above (441/441 frames).

```sh
V=data/private/mytronlabs-000060-016.mp4
L=data/private/labels_v2/labels_v2_provisional.json
T="--detection-threshold .3 --presence-threshold .3 --tracking-threshold .3"
uv run motioniq process $V --out runs/dev_B0 --duration 30 --no-video
uv run motioniq process $V --out runs/dev_chosen --duration 30 --no-video --preset recall      # = --rescue-crop $T
uv run motioniq process $V --out runs/hold_chosen --start-seconds 60 --duration 90 --no-video --preset recall
uv run motioniq identity runs/dev_chosen
uv run motioniq evaluate runs/dev_chosen $L --allow-provisional --split dev --summary
uv run motioniq quality runs/dev_chosen $V --labels $L --allow-provisional --split dev
uv run motioniq export-segments runs/dev_chosen --out runs/dev_chosen_suitable --status suitable
uv run motioniq lift runs/dev_B0 --hfov 120 150 180
uv run motioniq replay $V runs/dev_chosen --out runs/dev_chosen/review.rrd --quality runs/dev_chosen/quality
```

The bake-off scripts used for the tables are wrappers around these commands; the configuration names map to the flags in §2. Runs, labels and recordings stay in `data/` and `runs/`, which are git-ignored and private.

## Reverse-time detection pass (`--preset accurate`, 31 Oct 2026)

MediaPipe's landmark model sees one frame at a time; its VIDEO mode only carries the previous frame's hand region forward. Because runs are offline, a second detection pass runs **backwards in time** (bounded memory: 300-frame segments, each warmed up on the 30 frames after it), and hands it finds that the forward pass missed are added (forward results take precedence; duplicates by the landmark rule). Same host, same clip, provisional labels:

| Split | recall (forward) | recall + backward pass | Precision | Notes |
| --- | ---: | ---: | --- | --- |
| dev (choice) | 36/72 | **41/72** | 36/36 → 41/41 | Identical with the full pipeline, 2 workers, converged seam |
| holdout (once) | 39/78 | **46/78** | 39/40 → 46/48 | full 27/46 → 34/46; truncated unchanged 7/23 |

Cost: detector time about doubles (30 s of 1080p: 101 s end to end with 2 workers on 4 vCPUs). It does not help hands cut off at the bottom edge. The default stays `baseline`; the viewer's default stays `recall`.

## Hybrid detector: RTMDet hand boxes + MediaPipe / RTMPose (`--preset hybrid`, experimental, 31 Oct 2026)

Idea: MediaPipe finds hands with a palm detector, which misses hidden palms. RTMDet-nano (hand) proposes whole-hand boxes; MediaPipe reads each new box (21 points, 3D, side); where it still fails, RTMPose-m (hand) gives 2D points and `handfit` adds depth from the median MediaPipe hand. Models: OpenMMLab ONNX, Apache-2.0, onnxruntime on CPU; archives SHA-256-verified.

| Check (dev, provisional labels, one clip) | Result |
| --- | --- |
| RTMDet box at a labelled hand, whole 960 px frame, score ≥ 0.2 | 22/72 (43 boxes elsewhere) |
| Same with 2×2 overlapping tiles | 43/72 (144 boxes elsewhere, often the pink rollers) |
| Full pipeline, `recall` | 36/72, precision 36/36 |
| Full pipeline, `hybrid` | **36/72, precision 36/47** (11 false positives); 170 s vs about 50 s for 30 s with 2 workers |
| Depth for RTMPose-only hands vs MediaPipe's own 3D (120 MediaPipe hands, 2D fed in) | median 17.4 mm per joint after rigid alignment; a jointed-finger fit was worse (17.7 mm) and 4× slower |

**Rejected as a default.** The hands RTMDet adds are the ones MediaPipe still cannot read inside the box, and its extra boxes create false positives. RTMDet-nano is small and trained mostly on third-person images. The preset stays available, labelled experimental, only to try on other recording families; it is hidden unless `uv sync --extra hybrid` and `motioniq fetch-model --rtm` have run.

## Wrong-hand labels: what was measured (31 Oct 2026)

Two separate failures make the viewer show the wrong hand label:

1. **Ghost skeletons.** A track that misses a frame is drawn as "predicted" for up to 0.15 s. When the hand was re-detected under a new track (a rescue crop placed the wrist outside the wrist gate), the old track's ghost was drawn on top of the observed hand, often with the other side. **Fix (now in `recall`, `accurate`, `hybrid` via `--box-link`):** a just-missed track whose predicted box overlaps a hand observed this frame by more than 50% is reported `lost`, not `predicted`; an unmatched detection inside such a box keeps the old identity. Replayed on the same detections: ghost frames dev 1 → 0, holdout 10 → 6; recall, precision and identity fragments unchanged (observations are untouched).
2. **Left/right errors.** With two hands observed in one frame, both got the same side in 11/102 dev and 69/165 holdout frames; only 4/69 were the same hand detected twice. Pairing rules (force one left + one right, by MediaPipe's P(right), by position, or both) helped on dev (27 → 29 of 33) but **not on holdout** (33 → 32 of 38; 38 → 38 of 45), so **none was adopted**. Most same-side frames are unlabelled, so the cause (wrong side vs another person's hand) is not measurable with the current labels.
