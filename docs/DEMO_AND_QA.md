# Five-minute demo, slide outline and judges' Q&A

**Second user story: expert knowledge capture.** "Half the shop lives in one person's head." Record an expert once, then let others replay the hand motion, add step markers and notes, and look at the same moment from three 3D viewpoints (`egohand compare`, `--steps`). EgoHand Twin *complements* setup sheets, ERP and cross-training; it does not replace them. Whether the 3D view helps people describe a hand action better than plain video is **not yet measured** (test below).

**User story:** a data engineer preparing factory demonstrations for hand-motion analysis or robotics research needs to know which intervals hold usable hand motion, where reconstruction failed, and what to inspect first, with every result traceable to source frames.

**Before presenting:**
- Process clips in advance and say so.
- Use only the private submission folder or the local viewer; no factory frames on public slides.
- State the label status: provisional until a team member reviews the labels.

## Demo script (5:00)

| Time | Show | Say |
| --- | --- | --- |
| 0:00–0:30 | Source clip, 0–12 s (wiping a slab) | "Head-camera factory video: fisheye, back-of-hand views, cloth, blur, hands cut off at the bottom edge." |
| 0:30–1:15 | Rerun: video + hand-relative 3D, pause at about 6 s and orbit | "21 landmarks per hand and hand-relative 3D in meters. Spacing between hands in the 3D panel is for display only." |
| 1:15–2:00 | Same seconds: B0 vs chosen detector | "Out of the box, MediaPipe found about a quarter of labeled visible hands. Lower thresholds plus a center crop found half on a held-out interval, with 39 of 40 detections correct. The labels are provisional." |
| 2:00–3:00 | Quality time series + review-queue log; jump to the top item (12–17 s) | "Each one-second window says *suitable*, *needs review* or *insufficient evidence*, with the reasons. The top item, 12–17 s, has hands observed in 30–73% of frames per window (below 50% in four of five windows), missing-track gaps of 0.53–0.73 s, side changes in three windows and fast camera motion (44% of frame width per second) at 16 s. These values come from the final demo run `runs/final_demo` (`--preset recall`). Insufficient evidence means *no observed hand*, not *no hand*." |
| 2:45–3:00 | `egohand compare` image at 6 s: flat frame vs front/side/top 3D views of each hand | "Same instant, flat video vs 3D. The side view shows how flat the hand on the slab is. Hidden joints are the model's estimate, and this frame also shows a side error: the hand on the slab is labeled Right with p=0.57." |
| 3:00–3:30 | A predicted/lost interval | "Predictions are short, 2D only and grey; lost tracks have no coordinates. None of it counts as a detection." |
| 3:30–4:10 | `review_queue.csv`, `export-segments --status suitable`, segment manifest | "The engineer exports only suitable intervals. Every record keeps raw values, states, source hash, run id and frame range." |
| 4:10–4:40 | Results table (holdout) + one unresolved failure (hands gripping the slab edge at the bottom: 7/23 recovered) | "This is what we measured, with denominators. This failure remains." |
| 4:40–5:00 | Limits slide | "Hand-relative 3D, not factory coordinates. Camera-space depth is an experiment under an assumed lens. One clip, one recording family, provisional labels." |

## Pitch line and positioning

> "When half the shop lives in one person's head, EgoHand Twin records what their hands actually do — lets anyone replay it from any angle — and tells a data team which seconds are usable, uncertain or missing."

- EgoHand Twin **complements** ERP, setup sheets and cross-training; it never replaces them.
- The second market is robot-learning data teams. Name its limits: no robot export, no retargeting, not robot-tested, hand-relative coordinates.
- Lead with replay and evidence, not dashboards. Use worker-friendly language: knowledge capture, not monitoring.

## Slide and claim review checklist (run on every slide before presenting)

1. Does the slide serve a named decision, and say what it beats (ordinary video, setup sheet, ERP)?
2. Is uncertainty visible: observed/predicted/lost, side probability, units, coordinate frame, "provisional labels"?
3. Does every number carry its numerator, denominator and n, and point to the run or frames it came from?
4. Forbidden claims, none of which may appear:
   - "detects contact / force / grasp quality";
   - "measures productivity";
   - "ensures safety / quality";
   - "factory/world coordinates";
   - "robot-ready, proven";
   - "coverage = accuracy";
   - "replaces ERP / setup sheets / training";
   - any per-worker score or ranking.
5. Privacy: no factory frames, faces, screens or documents on public slides. Use our own consented recordings or drawings only.
6. Do the numbers match RESULTS_V2.md, with schema-valid outputs and passing tests?
7. Is setup still one command, offline and laptop-friendly?

## Slide outline (6 slides)

1. **Problem:** factory POV hand motion is valuable data but hard to extract and to trust; teams need to know which footage is usable.
2. **What we built:** video → hands + 3D → quality signals → review queue → traceable exports (diagram, no factory frames).
3. **How:** MediaPipe with lower thresholds and a center-crop rescue; tracker with explicit states; heuristic quality windows; provenance.
4. **Evidence:** dev/holdout recall and precision with denominators, side accuracy, quality-flag catch rate and false-alarm burden, timestamp-probe speed-up. Mark everything "provisional labels, one clip".
5. **Workflow value:** queue → inspect → export suitable segments. The review-time benefit is **not yet measured**; show the pilot protocol.
6. **Limits and next steps:** label review, other recording families, lens calibration, an own-recording depth test, privacy flags.

## Q&A pack

Each answer has: a short answer (20–30 s), its **evidence**, a longer technical explanation, and a **fallback** for what remains unmeasured.

**1. What does this add beyond MediaPipe?**
- *Short:* MediaPipe gives per-frame landmarks. We add a measured recovery step that doubles recall on held-out frames, persistent tracks with explicit missing states, a task-specific quality layer and review queue, and full provenance.
- *Evidence:* holdout recall 19/78 → 39/78 (RESULTS_V2 §3); state machine and tests; `quality/`; manifests with hashes.
- *Detail:* Hungarian association on wrist motion, shape and soft handedness; One Euro smoothing with raw values kept; predictions are 2D only; heuristic windows with reason codes; segment export.
- *Fallback:* meshes, calibrated camera space and robot export are **not** implemented.

**2. Why is this relevant to the company?**
- *Short:* they need to turn large volumes of egocentric footage into usable structured data and decide what is usable. We reconstruct hands and point reviewers to usable vs uncertain intervals, with evidence.
- *Evidence:* review queue and suitable-segment export on real footage.
- *Fallback:* we have not measured time saved or downstream model benefit.

**3. How do you tell a detector failure from a hand leaving the frame?**
- *Short:* not perfectly. We distinguish *observed*, *recently seen then missing* (predicted/lost) and *no observed hand*, and label the last one "insufficient evidence", never "no hand".
- *Evidence:* on holdout, 12 of 18 labeled frames in B0's insufficient-evidence windows had a visible hand. Visibility labels (full/occluded/truncated) give recall per category.
- *Detail:*
  - Each missing track carries `missing_reason`. `out_of_view` means the extrapolated wrist left the image or the hand was at the border; otherwise it is `unknown`. The evidence is shown in the replay log.
  - Measured on holdout: 6 of 15 `out_of_view` claims were contradicted by a labeled hand still nearby, and 21 of 23 `unknown` gaps had a visible but undetected hand. Mostly the detector misses the hand; it hasn't gone.
  - Edge-proximity flags mark hands at the boundary; missing-track gaps mark a hand that disappeared mid-interval.
- *Fallback:* no automatic visible-but-undetected classifier.

**4. Does your quality assessment predict downstream training performance?**
- *Short:* no, and we don't claim it. It is a task-specific assessment for hand-motion inspection.
- *Evidence:* the flags catch 22/35 missed-hand frames on holdout and keep 4/10 fully detected frames as suitable.
- *Fallback:* downstream training impact is untested.

**5. Are these real factory coordinates?**
- *Short:* no. The reported 3D is MediaPipe's hand-relative estimate in meters around each hand's center, and display spacing between hands is arbitrary.
- *Evidence:* `COORDINATES` in the manifest; README coordinate contract.
- *Detail:* an experimental PnP lift puts hands in *camera* coordinates under an assumed lens. Depth moves ±25% with the assumed FOV, and the residual cannot tell lenses apart.
- *Fallback:* no world or factory frame and no SLAM.

**6. How do you know accuracy improved?**
- *Short:* the configuration was chosen on dev labels and scored once on a held-out interval, under the same matching rule and the same host.
- *Evidence:* dev 17/72 → 36/72, holdout 19/78 → 39/78, precision 39/40, Wilson intervals, 0.10-diagonal gate with an audit at 0.05.
- *Fallback:* the labels are provisional (not human-reviewed); one clip and one family; the holdout is temporal, not cross-family.

**7. Does smoothing or prediction hide failures?**
- *Short:* no. Raw and filtered values are stored separately; predicted states are 2D-only and excluded from detection metrics; lost tracks have null coordinates.
- *Evidence:* `test_predicted_hands_do_not_inflate_recall`, `test_occlusion_is_not_a_3d_observation...`; evaluation uses `image_xyz_raw` of observed hands only.

**8. How reliable is left/right?**
- *Short:* per-frame side is correct for 32/38 matched wearer hands on holdout with the chosen detector, and 19/19 with B0. Recovered hard cases are less reliable.
- *Evidence:* RESULTS_V2 §4; no mirroring needed (25 vs 8 on dev).
- *Detail:* track IDs are short-term associations, not anatomical identity. The offline vote allows *unknown*. Background hands are not classified as "other".
- *Fallback:* no wearer-vs-other classifier.

**9. What happens with false quality flags?**
- *Short:* nothing is deleted. Flags only order human review, and false alarms are measured.
- *Evidence:* about 12 review items per minute; 6/10 fully detected holdout frames sit in needs-review windows; `export-segments` copies intervals without changing the run.
- *Fallback:* the thresholds are not validated beyond this clip.

**10. Is the system privacy/compliance certified?**
- *Short:* no. We have no privacy detector. Each run records purpose, consent status, retention date, redaction status and lens source in its manifest. Processing refuses runs past their retention date, and `retention-report` lists runs for deletion review. These are operator statements, not verified compliance. Footage and outputs stay private and are ignored by git.
- *Fallback:* candidate face/screen/text flags are future work and need a labeled evaluation set.

**11. Can it process the whole dataset (about 100 TB)?**
- *Short:* not demonstrated. On a 4-vCPU VM, 30 s of 1080p footage processes in 55–59 s with B0 and 85–87 s with the chosen detector (all outputs), and quality analysis reruns from cache in 8.3 s. We removed a per-clip timestamp bottleneck (129 s → 57 s end-to-end).
- *Detail:* a plausible design is per-clip jobs across many CPU workers, caching observations once and rerunning quality analysis cheaply from the cache. It is untested at scale.

**12. What industrial benefit have you demonstrated?**
- *Short:* a working review workflow on real footage. The time saved is **not yet measured**.
- *Evidence:* pilot protocol below.

**13. Is the export ready to control a robot?**
- *Short:* no. There is no robot export, retargeting or robot testing. The structured exports are research data.

**14. Why not meshes or SLAM?**
- *Short:* hand tracking carries the most points, and detection was the bottleneck: 3D only exists where a hand is found. Meshes need a GPU and MANO assets we don't have; SLAM doesn't provide hand depth. We measured the assumed-lens lift and found depth too uncertain to headline.

**15. What remains unsolved?**
- Hands gripping objects at the bottom edge (7/23 recovered on holdout) and side views.
- Side errors on recovered hands, and track fragmentation.
- Labels not yet human-reviewed; no other recording family; unknown lens.
- *Next experiments:* review the labels; process one clip from each other family; a calibrated own-recording depth test; try a dedicated hand detector for edge and grip cases.

## "Does 3D beat video?" user test (protocol; not yet run)

- **People:** 3–5 participants who did not build the tool.
- **Tasks:**
  - (a) "Find the moment the cloth hand reaches the far edge."
  - (b) "Describe how the hand on the slab is posed: flat or curled, fingers spread or together."
- **Conditions:** plain video, vs video + 3D replay + `compare` image, counterbalanced across two clip intervals.
- **Record:** time; correctness against answers agreed by two reviewers beforehand; confidence.
- **Report:** results per task, with n. If 3D does not beat video on (b), say so and present the steps sidecar and review queue as the value instead.

**Q16. Does 3D show anything video can't?**
- *Short:* untested. The 3D view gives other viewpoints of the same instant, but hidden joints are the model's estimate, not an observation. We built the comparison and a test protocol; we have no measured result.
- *Fallback:* the steps sidecar and review queue stand on their own.

## Review-time pilot (protocol; not yet run)

- **Task:** for a 90 s clip, list every interval longer than 1 s where hand reconstruction is missing or unreliable, plus three intervals suitable for export.
- **Conditions:** A, ordinary video player; B, Rerun replay with the quality timeline and `review_queue.csv`. Use two different clips of similar difficulty, counterbalanced across reviewers, so no one reviews the same clip twice.
- **Ground truth:** frame-labeled intervals reviewed by a person who does not take the test.
- **Record:** completion time; correct, missed and false intervals; number of participants and clips.
- With a single participant, report it as an exploratory pilot. Do not report any time saving until it is run.
