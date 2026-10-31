# Definitions (frozen 31 Oct 2026, label schema 2.0, manifest schema 0.5)

These definitions govern every label, metric and claim in this repository. Changing one means bumping the relevant schema version and re-running the affected evaluations; results computed under different definitions are not compared.

## Frames and hands

| Term | Definition |
| --- | --- |
| **Eligible frame** | A processed source frame inside a labeled interval that no `conditions.json` interval marks `excluded`. Excluded frames are reported with their reasons, never silently dropped. |
| **Visible (labelable) hand** | Some of the palm or back of the hand, the region between wrist and knuckles, is visible. Fingertip-only or forearm-only views are not labelable. Distant background hands smaller than about 40 px are treated as not labelable. Every labelable hand in a labeled frame must be listed, including other people's hands. |
| **Wrist point** | Centre of the wrist joint (MediaPipe landmark 0), in normalized source-image coordinates. It may lie just outside the image only with `wrist_in_frame=false`. |
| **Visibility** | `full`: hand essentially unobstructed and inside the image. `occluded`: part of the hand covered, for example by a cloth or object. `truncated`: hand cut by the image boundary. |
| **Anatomical side** | `wearer_left`, `wearer_right`, `other` (another person's hand) or `unknown`. Never forced; `unknown` is a valid answer. It is distinct from the classifier's per-frame Left/Right and from short-term track IDs. |

## Tracker states

| State | Meaning | Coordinates |
| --- | --- | --- |
| `observed` | Detected in this frame. | Raw and filtered 2D and 3D. |
| `reacquired` | Detected again after being missing, before retirement. | Raw and filtered 2D and 3D. |
| `predicted` | Missing for at most 0.15 s; position extrapolated. | **2D only**, extrapolated; no 3D; never counted as a detection. |
| `lost` | Missing for more than 0.15 s and at most 0.8 s. | None. |
| `retired` | Missing for more than 0.8 s; the ID is never reused. | None. |
| `missing_reason` | For non-observed states. `out_of_view` (inferred: the extrapolated wrist left the image, or the last landmarks touched the border) or `unknown`. A hint, not an observation. | — |

A **track ID** is a short-term association. It may change after a hand leaves view, and it is not an identity claim about a person.

## Metrics

Every metric is reported with its numerator, denominator and n, and per split. Results from provisional labels are stamped `provisional`.

| Metric | Definition |
| --- | --- |
| **Frame coverage** | Processed frames with at least one *observed* hand ÷ processed frames. Coverage is not recall or accuracy. |
| **Match** | One-to-one Hungarian assignment between labeled wrists and *observed* raw predicted wrists, gated at 0.10 image diagonals. The gate is audited at 0.05. |
| **Visible-hand recall** | Matched labeled hands ÷ labeled hands in eligible frames. |
| **Precision** | Matched predictions ÷ observed predictions in eligible labeled frames. False positives outside labeled frames are not counted. |
| **Side accuracy** | For matched hands labeled `wearer_left`/`wearer_right`: predicted side equals the labeled side ÷ such matches. Reported per frame, track-smoothed and as the offline vote. Results under the mirrored convention are shown alongside. |
| **ID changes** | Consecutive labeled samples of one labeled hand, within one interval, whose matched track ID differs ÷ such sample pairs. Sampled at labeled frames only. |
| **Fragments** | Distinct track IDs matched to one labeled hand within one interval (1 = unfragmented). |
| **Predicted run / bridged gap** | Length of consecutive `predicted` samples of a track / time between two observed samples of the same track. Run-level statistics, not compared with labels. |
| **PCK** | Fraction of labeled joints within 0.03 image diagonals on matched hands. Conditional on a match; misses are reported separately. |
| **Grip aperture** (not implemented) | 3D distance from thumb tip (landmark 4) to index tip (landmark 8) in metres. A distance only: not force, not proof of grasp or contact. |
| **3D error** | Only against independent 3D ground truth (a calibrated own recording). Not measured. |
| **FPS** | End-to-end processing throughput and detector-only throughput are reported separately, with per-stage seconds. |

## Splits and annotation rules

- **Development** labels are used for tuning; the **holdout** is scored once, after choices are frozen.
- Splits are contiguous source intervals; adjacent frames never cross a split.
- With more data, split by recording session, clip and recording family. The current holdout is temporal, from the same clip and family.
- Label before looking at predictions. Record provenance (annotator, method, model assistance, review status).
- `reviewed=true` only after independent human review. A subset should be dual-labeled and agreement reported.
- Capture conditions (`glove_ppe`, `occlusion`, `lighting`) and exclusions are human annotations in `conditions.json`, bound to the source video.

## Coordinate frames and units

| Field | Frame and units |
| --- | --- |
| `image_xyz*` | x/width, y/height of the source frame; z is MediaPipe wrist-relative depth in roughly x units (not metric). |
| `world_xyz_m*` | MediaPipe hand-relative metres, origin near the hand's geometric centre. Not camera, world or factory coordinates. |
| `lift_*` (experimental) | Camera frame, metres, x right, y down, z forward, under an **assumed** lens; depth unvalidated. |
