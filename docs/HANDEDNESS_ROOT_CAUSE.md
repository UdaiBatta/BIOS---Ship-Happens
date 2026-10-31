# Why a hand's left/right label flips

**Symptom (team recording and screenshots):** the hand wiping with a cloth changed from "Wearer left" to "Wearer right". Separately, two hands both showed the same side, and a second skeleton was sometimes drawn on one hand.

**Root cause, measured on the labelled clip** (provisional labels; flips are side changes between consecutive labelled samples of one labelled hand):

| Run | Flips | Inside one track | At a track change |
| --- | ---: | ---: | ---: |
| `recall`, dev | 7 | 3 | 4 |
| `recall`, holdout | 8 | **7** | 1 |
| `accurate`, holdout | 10 | **7** | 3 |

Most flips happen **inside one track**, so the tracker's own side state is the problem, not identity association.

1. **How the side was set.** The tracker kept a running P(right) = 0.85·previous + 0.15·this frame's MediaPipe score, and showed Right whenever P ≥ 0.5.
2. **Weak evidence was trusted.** MediaPipe's left/right is much worse on hands found by the centre-crop rescue: correct for 10/17 labelled holdout hands, against 26/32 for full-frame detections. Dev: 7/11 against 18/22. A few crop frames in a row (exactly the cloth, fist and edge situations that need the crop) moved P across 0.5.
3. **No hysteresis.** A hand near 0.5 flickered every few frames: 29 Left↔Right changes inside tracks over the holdout run.

Ruled out:
- **Image mirroring.** MediaPipe's label matches the wearer's side on this camera (25 vs 8 on dev). No step in the pipeline flips images.
- **The whole-track vote** (`identity.json`, shown when loaded). Removing crop frames from it changed nothing on dev (27 → 27 and 32 → 33 correct), so it was left as is.
- **Screen position.** Never used to decide the side.

**Fix** (`tracking.IdentityTracker`; on in the `recall`, `accurate` and `hybrid` presets):
- `crop_side_weight = 0`: crop-rescue detections keep the track's side.
- Neutral-score detections (RTMPose-only, score 0.5) never move it; the record says `side_source: inherited_from_track`.
- A track with no side evidence yet shows **`unknown`** instead of guessing.
- `side_hysteresis = 0.15`: the shown side changes only when P passes 0.65 / 0.35.

Chosen among six variants on dev, checked once on holdout. Same detections, tracking replayed. Matched labelled wearer hands; "unknown" counts as not correct; flips count only Left↔Right changes:

| Split, run | Wrong side | Unknown | Correct | Labelled L↔R flips (inside a track) | L↔R changes within tracks, whole run |
| --- | --- | --- | --- | --- | --- |
| dev, `recall` | 6 → 5 | 0 → 7 | 27 → 21 of 33 | 7 (3) → 6 (3) | 18 → **3** |
| dev, `accurate` | 5 → 3 | 0 → 7 | 33 → 28 of 38 | 5 (3) → 5 (2) | 23 → **3** |
| holdout, `recall` | **11 → 5** | 0 → 12 | 38 → 32 of 49 | **8 (7) → 2 (1)** | 29 → **3** |
| holdout, `accurate` | **11 → 7** | 0 → 6 | 43 → 41 of 54 | **10 (7) → 2 (2)** | 36 → **4** |

**Reading this honestly:** wrong labels roughly halve on holdout, and the visible flicker almost disappears. The cost is that hands the tracker has no reliable evidence for (mostly tracks that start on a crop detection, such as the cloth hand) say `unknown` instead of guessing. The old guess was right more often than not, which is why "correct" drops. The viewer's whole-track vote (`identity.json`, loaded for backend runs) still assigns those tracks a side from all their frames.

**Same-side pairs and ghosts** (see [HYBRID_TRACKING_AUDIT](HYBRID_TRACKING_AUDIT.md)):
- **Ghosts** are fixed by `--box-link`: dev 1 → 0, holdout 10 → 6.
- **Same-side pairs** (42% of two-hand holdout frames) remain. A one-left/one-right rule did not hold up on holdout.

Regression tests: `tests/test_handedness.py` (Test 1) and `tests/test_3d_availability.py` (Tests 7–8).
