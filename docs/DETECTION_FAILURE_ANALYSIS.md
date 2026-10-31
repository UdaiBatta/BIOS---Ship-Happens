# Detection failure analysis

One clip, provisional labels (not yet human-reviewed). Matching is one-to-one: a raw observed wrist within 0.10 image diagonals of the labelled wrist. Predicted and interpolated hands never count.

## 1. Failure categories with their denominators (holdout, `recall` preset)

The previously reported miss counts are misses out of these labelled totals. **Tags overlap**: a missed hand carries 0–3 tags, so the rows must not be summed.

| Tag | Missed | Labelled | Recall |
| --- | ---: | ---: | ---: |
| holding an object | 21 | 36 | 0.42 |
| side view | 18 | 30 | 0.40 |
| image edge | 16 | 23 | 0.30 |
| cloth | 5 | 14 | 0.64 |
| fist | 4 | 6 | 0.33 |
| holding a tool | 4 | 5 | 0.20 |
| back of hand | 3 | 15 | 0.80 |
| all hands | 39 | 78 | 0.50 |

## 2. Still hands

Labelled samples whose wrist moved less than 0.05 normalised image units per second to the hand's next labelled sample (the last sample of each hand has no speed and is left out):

| Split, preset | Still samples found | Moving samples found |
| --- | ---: | ---: |
| holdout, `recall` | 10/19 | 37/53 |
| holdout, `accurate` | 11/19 | 41/53 |

On dev, the bare left hand resting on the slab (back of the hand to the camera, the team-recording case) is found in 14/30 of its labelled samples with `recall` and 18/30 with `accurate`. Across all dev hands tagged back-of-hand, the gated hybrid finds 19/32, against 16/32 with `recall`.

Likely cause: MediaPipe's palm detector sees almost the same image every frame, so a hand it rejects stays rejected. The detection threshold is already 0.3. No suppression bug was found: duplicate suppression only removes a candidate that matches an already-found hand point by point.

## 3. Where the hybrid recovers misses (dev, the 36 hands `recall` misses)

| Stage | Hands | Note |
| --- | ---: | --- |
| B2: an RTMDet hand box (2×2 tiles, score ≥ 0.2) covers the wrist | 20 | The whole frame at 320 px input covers only 22/72 of all labelled hands |
| B3: MediaPipe reads it inside a padded square crop | 0 at threshold 0.3; 3 at 0.1 | Its palm detector rejects in the crop what it rejects in the frame |
| B4: RTMPose's wrist lands on the labelled wrist | 19 | Low scores: median 0.27; only 1 ≥ 0.45 |

Wrong boxes (skin-coloured rollers) get RTMPose scores as high as real hands, so no score threshold separates them. A **track gate** does: accept a recovered hand only within 0.15 diagonals of a hand seen in the last 0.8 s that is missing now. At score ≥ 0.25 that gives 8 real and 1 wrong, against 10 and 11 without the gate.

Per-category effect on dev (`recall` → gated hybrid, RTMPose fallback only):
- back of hand: 16 → 19 of 32
- cloth: 16 → 20 of 31
- edge: 5 → 6 of 10
- blur: 3 → 5 of 6
- holding a tool: 2 → 3 of 4

The holdout check is in [EXPERIMENT_RESULTS](EXPERIMENT_RESULTS.md).

## 4. What each failure needs

| Failure | Type | What helped (measured) | Not solved |
| --- | --- | --- | --- |
| Hidden palm (object, tool, fist, back of hand) | detection (palm detector) | centre crop; reverse-time pass; RTMPose fallback near a known track | Hands never tracked before (the gate needs a recent track) |
| Image edge, bottom | detection | little: holdout 7/23 recovered with `recall` | A detector trained on truncated egocentric hands |
| Cloth | detection, then landmarks | RTMPose fallback (dev 16 → 20 of 31) | Landmarks over the cloth are often wrong even when found |
| Wrong side | identity | see [HANDEDNESS_ROOT_CAUSE](HANDEDNESS_ROOT_CAUSE.md) | About 1 in 5 matched hands is still wrong from the start |
