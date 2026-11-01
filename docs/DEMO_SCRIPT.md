# Final demo: status, script and presentation guide (1 Nov 2026)

This is the presenter's guide for the final pitch. It **replaces the 5-minute script in [DEMO_AND_QA](DEMO_AND_QA.md)**. That script was written for the Rerun replay, before the web viewer existed. DEMO_AND_QA is still the long-form Q&A reference.

Every number here comes from [RESULTS_V2](RESULTS_V2.md), [EXPERIMENT_RESULTS](EXPERIMENT_RESULTS.md), [SMOOTHING_COMPARISON](SMOOTHING_COMPARISON.md), [PERFORMANCE_REPORT](PERFORMANCE_REPORT.md) or [PLAYBACK_PERFORMANCE](PLAYBACK_PERFORMANCE.md). **All accuracy figures come from one clip with provisional labels.** Say so whenever you show one.

---

## 1. Where the project stands

### At a glance

| | |
| --- | --- |
| **Product** | EgoHand Twin reconstructs hand motion from head-mounted factory video, offline on a laptop CPU. It shows which seconds are **usable, uncertain or missing**, and every number traces back to source frames. |
| **Category** | PS4: 3D hand motion |
| **Users** | (1) A data engineer preparing hand-motion data for analysis or robot learning. (2) Expert knowledge capture: replay an expert's hands from any angle. |
| **Interface** | One command (`scripts/run_local.sh`) starts the Django backend, the job worker and the web viewer at `http://127.0.0.1:8000/`. |
| **Tests (re-run 1 Nov)** | Pipeline **156 passed, 3 skipped**; backend **42/42**. Viewer loads without page errors. |
| **Git history** | No media, data or model files (`scripts/check_history.sh`). |

### What works (demo these)

| Capability | Evidence you can quote |
| --- | --- |
| 21 2D landmarks + 21 hand-relative 3D landmarks per hand (MediaPipe) | Runs on real factory footage |
| **Detection recovery presets** | Holdout visible-hand recall: `baseline` **19/78** → `recall` **39/78** (39/40 correct) → `accurate` **46/78** (46/48 correct). F1 0.39 → 0.66 → 0.73. |
| Tracking with explicit states: observed / predicted (2D only, ≤0.15 s) / lost / retired / reacquired | Predictions never count as detections and never carry 3D |
| **Left/right fix**: `unknown` instead of guessing | Wrong side 11/49 → **5/49**; left↔right flicker within tracks 29 → **3** |
| **Smoothing fix**: offline RTS wrist + One Euro fingers; raw values always kept | Lag 65 → **6 px**; wrist jitter halved; wrist error back to raw level (holdout median 26.6 px vs 25.3 raw) |
| **Web viewer**: Review / Analysis / Diagnostics workspaces | Video + 2D skeleton, 3D hands (skeleton / mesh / both), timeline lanes, events, frame details, export |
| Timeline: per-hand lanes + Unknown-side lane, events strip, zoom/scrub, **F = next failure, R = next reacquisition**, inspection panel | Checked in Chromium on real runs |
| **Evidence-linked motion events** (entry/exit, long gap, candidate hold/movement) with **Confirm/Reject** stored on the server | Human in the loop. Thresholds are unvalidated heuristics. |
| Quality windows (suitable / needs review / insufficient evidence), ranked review queue, `export-segments --status suitable` | Flags catch 22/35 missed-hand frames on holdout; about 12 review items per minute |
| Frame-exact playback | Overlay vs displayed frame mismatches **173/179 → 0/180** |
| Speed | 30 s clip end to end **129 s → 57 s** (timestamp-probe fix). Recall preset with 2 workers: 46.5 s for 30 s on a 4-vCPU VM. |
| Provenance and governance | Source/model SHA-256, run id, JSON Schema validation, consent/retention fields, `retention-report` |
| Exports | JSONL / CSV / NPZ, events CSV, Aria-compatible CSV, Rerun `.rrd` |

### Tried, measured and rejected (strong judge material: it shows discipline)

- **`hybrid` preset** (RTMDet + RTMPose). +10 points recall on holdout, but precision fell 0.975 → 0.887 and it ran 2.6× slower. That **fails the go/no-go rule we fixed before testing**, so it stays opt-in.
- **Face privacy flags.** 2/2 candidates were false alarms and distant people were missed. **Not shipped** to the viewer.
- **Still-hand discovery, lower thresholds, 1280 px input, bottom-padded crops.** None gained on dev, so none was run on holdout.

### Not done (say it before the judges ask)

- **Labels are provisional.** One annotator, not yet reviewed by a person. **One clip, one recording family.** The holdout is a later part of the same clip.
- **No fitted meshes (MANO/WiLoR/HaMeR).** The viewer's mesh is a joint-skinned visual surface. Fitted meshes are blocked by the licence, the GPU and the weights. A `mesh_*.npz` loader is ready.
- **No validated depth or world coordinates.** Camera-space 3D uses an **assumed** fisheye lens (HFOV 150°). Depth moves ±25% with that assumption.
- **No camera-motion compensation.** Head motion counts as hand motion.
- **User tests (3D vs video, review-time pilot)** are written up as protocols but **have not been run**.
- **Timings come from a cloud VM**, not the team laptop.

### Fix in the docs before judges read the repo (≈15 min)

| Where | Says | Actually |
| --- | --- | --- |
| README → Repository structure | "91 core tests; 9 API tests" | 159 pipeline tests (156 pass + 3 skipped), 42 API tests |
| README → Status table, last row | Bone calibration, privacy flags, action events: "Not implemented" | Bone calibration is **done**; motion events are **done** (heuristic); privacy flags are **experimental, not useful yet** |
| README Status table, `frontend/README.md` | Mesh is "432 vertices" | Current mesh: 970 vertices / 1,872 triangles ([HAND_MESH_ARCHITECTURE](HAND_MESH_ARCHITECTURE.md)) |
| [SUBMISSION](SUBMISSION.md) "What is implemented" | "Eleven focused automated tests" (historical list) | Update or mark the list as historical |

### Highest-value work before submission (in order)

1. **A teammate reviews the labels** (about 45 min: `egohand label-review` → `label-review-apply` → re-run RESULTS_V2 §8). This turns every "provisional" into a real number and is the biggest credibility gain available.
2. **Record the backup demo video** (section 4).
3. **Build the 6 slides** (section 2).
4. If there's time: run the **review-time pilot** with 2–3 people ([USER_TEST_PROTOCOL](USER_TEST_PROTOCOL.md) §2, 30 s interval). Even a tiny measured result is better for "industrial usefulness" than "not measured".
5. Process one clip from another recording family on the laptop and show it unlabelled, as a generalisation sanity check.

---

## 2. What to present: 6 slides + live viewer

The live viewer is the main content. Slides only frame it. **No factory frames on any slide.** Use diagrams, or the synthetic-demo screenshot, which is badged "SYNTHETIC DATA".

| # | Title | Content |
| --- | --- | --- |
| 1 | **EgoHand Twin** | One line: *"Replays what workers' hands actually do in 3D, and tells you which seconds you can trust."* Team Ship Happens · PS4. |
| 2 | **The problem** | Head-camera factory video: fisheye, blur, cloth, gloves, back-of-hand views, hands cut off at the bottom edge. Out of the box, MediaPipe finds about **1 in 4** visible hands (19/78). Data teams can't tell usable footage from garbage without watching all of it. |
| 3 | **What we built** | Diagram: `video → hands (2D + hand-relative 3D) → tracks with explicit states → quality windows + events → review viewer + traceable exports`. Runs offline on a CPU, one command, data stays on the laptop. |
| 4 | **Evidence** | Table A below, plus 3 one-liners: side errors 11 → 5 of 49; smoothing lag 65 → 6 px; playback mismatches 173 → 0. Footer: *"Provisional labels · one clip · holdout scored once after choosing on dev."* |
| 5 | **Rigor: what we rejected** | Hybrid detector: +10 points recall, but it failed our pre-registered precision rule, so it isn't the default. Face privacy flags: 2/2 false alarms, so not shipped. *"We only ship what we measured."* |
| 6 | **Limits and next steps** | Hand-relative 3D, not factory coordinates. Provisional labels on one clip. No fitted meshes. Next: label review, other recording families, lens intrinsics, MANO/WiLoR on a GPU, review-time pilot. |

**Table A (slide 4), holdout set, 78 labelled visible hands:**

| Preset | Recall | Precision | F1 |
| --- | ---: | ---: | ---: |
| `baseline` (MediaPipe defaults) | 19/78 (24%) | 19/19 | 0.39 |
| `recall` (thresholds 0.3 + centre crop) | 39/78 (50%) | 39/40 | 0.66 |
| `accurate` (+ reverse-time pass) | **46/78 (59%)** | 46/48 | **0.73** |

---

## 3. Demo script (5:00, word for word)

**Setup on screen:** the browser at `http://127.0.0.1:8000/`, **Review** workspace, split **Balanced**, 3D mode **Ours · approx. camera-space**, **Smoothed**. Load the prepared run with **Load run**: the 60–150 s holdout interval processed with `recall` or `accurate`. The video is paused at the start of the segment and the debug-labels switch is off. Slides are in a second window.

Replace the `⟨…⟩` placeholders with the moments you note during the pre-flight (section 4, step 5).

### 0:00 – 0:30 · Hook (slides 1–2)

> "Factory workers wear head cameras, and that footage is valuable training data. But it's brutal: fisheye, blur, cloth, hands half out of frame. Out of the box, MediaPipe found only about one in four visible hands on our held-out frames.
> Worse, nobody can tell which seconds are usable without watching all of it. EgoHand Twin fixes both."

*Switch to the browser.*

### 0:30 – 1:20 · See the hands (Review workspace)

*Press Space to play about 6 s, then pause on a two-hand frame ⟨T_both⟩.*

> "Left is the real head-camera video with 21 landmarks per hand. Orange is the wearer's left hand and blue is the right. Each label says how the hand was found: full frame or a rescue crop.
> Right is the same instant in 3D."

*Drag to orbit the 3D view. Toggle **Skeleton → Mesh + skeleton**, then switch to **Baseline · hand-relative** and back.*

> "You can orbit it and see grip shape and finger posture that the flat video hides. Watch the labels: this is an approximate camera-space view under an *assumed* lens. Every depth reads '≈ estimated', and the surface is generated from the joints, not a fitted hand model. We never show more confidence than we have."

### 1:20 – 2:15 · Find failures instantly (timeline)

*Point at the lanes.*

> "This is the timeline. There's one lane per hand, plus an *Unknown side* lane, because when we aren't sure which hand it is, we say so instead of guessing. That cut left/right flicker from 29 to 3."

*Press **F** to jump to the next tracking failure ⟨T_fail⟩. Click the lane to open the inspection panel.*

> "F jumps straight to the next tracking failure. For up to 0.15 seconds a missing hand is shown as a grey 2D prediction. It's never counted as a detection and never gets invented 3D. After that it's *lost*, with no coordinates at all. The panel shows why it's missing and how the hand was found."

*Press **R** to jump to the reacquisition.*

> "R jumps to where it's reacquired. A reviewer can step through every problem in a clip without scrubbing the video."

### 2:15 – 2:45 · Human in the loop (events)

*Click a **candidate hold** or **long gap** in the events strip ⟨T_event⟩, then click **Confirm** or **Reject**.*

> "We also derive candidate motion events, such as a hand holding still or a long gap, each linked to its evidence frames. They're *candidates*: the reviewer confirms or rejects them, and the decision is stored on the server and survives a reload."

### 2:45 – 3:45 · Evidence (slides 4–5)

> "Here's what we measured on a held-out interval we scored only once, after choosing every setting on a separate dev interval.
> Baseline MediaPipe found 19 of 78 visible hands. Our recall preset finds 39 with one false positive. The accurate preset adds a reverse-time pass, which works because we're offline, and reaches 46 of 78.
> We also fixed left/right errors, cut smoothing lag from 65 pixels to 6, and made the overlay frame-exact."

*Switch to slide 5.*

> "Just as important is what we *didn't* ship. A hybrid detector gave 10 more points of recall, but it failed the precision rule we wrote down before testing, so it isn't the default. A face-privacy detector produced only false alarms, so it's not in the product.
> These labels are still provisional and come from one clip. We'll show you the denominators every time."

### 3:45 – 4:30 · Industrial workflow (Analysis workspace)

*Click the **Analysis** tab and point to the events list and export. Optionally show `quality/review_queue.csv` in a terminal.*

> "For a data engineer, the Analysis workspace shows the timeline, motion signals and events without the video. The pipeline labels each second *suitable*, *needs review* or *insufficient evidence*, with reasons, and ranks a review queue. You export only the suitable segments, as JSONL, CSV, NumPy, or an Aria-compatible CSV. Raw and smoothed values, source hash and run id travel with every record.
> It's one command on a laptop, and the footage never leaves the machine."

### 4:30 – 5:00 · Close (slide 6)

> "To be clear about scope: the 3D is hand-relative, not factory coordinates. Depth uses an assumed lens. Fitted MANO meshes need a GPU and a licence, and our loader is ready for them.
> Next we review the labels, test the other recording families and get the lens intrinsics.
> EgoHand Twin: see what the hands did, and know exactly when to trust it. Thank you."

---

## 4. How to present

### Roles
- **Speaker:** delivers the script and owns the slides.
- **Driver:** operates the viewer and never speaks over the speaker. Practise the hand-offs at 0:30, 1:20, 2:45 and 3:45.
- **Q&A lead:** the person who knows RESULTS_V2 best. Everyone else says "good question, [name] measured that".

### Pre-flight (on the demo laptop, ≥ 30 min before)

1. `git pull` on `udai-s1`, then run `bash scripts/run_local.sh` (Windows: `scripts\run_local.ps1 -Test`). The launcher stops old servers, so stale code can't be served.
2. **Process the demo runs in advance. Never click Process live as the main path.** A 30 s `recall` run takes about 50 s plus about 25 s for the proxy on the VM, and the laptop is unmeasured. Prepare:
   - `recall` on 60–150 s (main demo; same interval as the holdout numbers);
   - optionally `accurate` on the same interval, to switch to if asked "what's your best mode?".
3. Open the run with **Load run**. Check that the video selector shows the right clip and the segment reads "60–150 s".
4. Set **Review**, **Balanced**, **Ours · approx. camera-space**, **Smoothed**, mesh **Mesh + skeleton**, and debug labels **off**.
5. **Find and write down your moments:**
   - ⟨T_both⟩: a frame with both hands observed and correct sides. Check the colours against the real hands.
   - ⟨T_fail⟩: the first **F** jump that lands on a visible, understandable gap (avoid ones where the hand is clearly still on screen, unless you want to discuss detector misses).
   - ⟨T_event⟩: one candidate event that's easy to judge by eye.
6. Do a full rehearsal with a stopwatch, aiming for **4:45**. Do at least two.
7. **Record the full run-through as an MP4 backup** (screen recording; keep it private). Put it on the laptop desktop and on a USB stick.
8. Turn off notifications and close Drive, Slack and email tabs. Set the display to mirror or a fixed resolution. Zoom the browser so timeline labels are readable from the back of the room.
9. Have a terminal ready at the repo root (large font) in case you show `review_queue.csv` or `metrics.json`.

### Fallback ladder (don't debug on stage)

| Failure | Do this |
| --- | --- |
| Server or viewer won't load | Re-run `scripts/run_local.sh`. If it isn't up within 30 s, play the backup MP4. |
| Video proxy doesn't play | **Load JSONL** + **Load video** from `runs/<run>/` (file mode, fully offline). |
| Laptop dies | Backup MP4 from the USB stick on any machine, plus the slides. |
| Judge asks to see it process live | Queue a **5 s** segment with Process during Q&A; it finishes while you talk. Rehearse this once first. |

### Delivery tips
- Your memorable story is **"we show when not to trust it"**. Hit it three times: the honest 3D labels (0:30), the predicted/lost states (1:20) and the rejected experiments (2:45).
- **Always give denominators** ("39 of 78"), never bare percentages, and say "provisional labels" once per evidence slide.
- Use these words: *hand-relative 3D*, *approx. camera-space*, *candidate events*, *knowledge capture*. Never use: *factory coordinates*, *real-time*, *detects grasp/contact*, *measures productivity*, *robot-ready*, *fitted mesh*, or *accuracy* for coverage.
- Point at the screen when you name colours or states. Judges at the back can't read the legend.
- Speak about **processes, never individual workers**. This is knowledge capture, not monitoring.
- **Privacy:** the viewer stays on `127.0.0.1`. No screenshots of footage in public decks or posts. Processed clips go only in the organisers' private folder.

---

## 5. Q&A: top 10 (30-second answers)

The long-form versions with evidence and fallbacks are in [DEMO_AND_QA](DEMO_AND_QA.md#qa-pack).

| Question | Answer |
| --- | --- |
| **What do you add beyond MediaPipe?** | Recovery presets that double recall on held-out frames, tracking with explicit missing states, a left/right fix, low-lag smoothing that keeps raw values, quality windows, a review queue, candidate events with human confirmation, full provenance and a review viewer. |
| **How accurate is it?** | Holdout recall: 39/78 with `recall` at 39/40 precision, and 46/78 with `accurate` at 46/48. The labels are provisional: one annotator, one clip, not yet reviewed by a person. Landmark accuracy (PCK) and 3D error are not measured; we have too few landmark labels and no 3D ground truth. |
| **Is the 3D real?** | The hand-relative 3D is MediaPipe's estimate in metres around each hand. Camera-space depth uses an assumed lens and moves ±25% with that assumption, so the viewer labels it "≈ est.". The mesh is generated from the joints, not fitted. |
| **Why not MANO/WiLoR meshes?** | They need a non-commercial licence with registration, multi-GB weights and a GPU, and the download hosts were blocked in our build environment. The viewer already loads `mesh_*.npz`, so fitted meshes are a drop-in once available. |
| **Why not use the hybrid detector, since it finds more hands?** | It failed the go/no-go rule we set before testing: +10 points recall, but −8.8 points precision and 2.6× the time. `accurate` has the better F1 (0.730 vs 0.718). |
| **What's still hard?** | Hands gripping objects at the bottom edge (7/23 recovered), side views, and still hands, which MediaPipe's palm detector keeps rejecting. About 1 in 10 matched hands still has the wrong side. |
| **Is it real-time?** | It's built as an offline review tool. About 19 FPS end to end for the `recall` preset with 2 workers on a 4-vCPU VM. We haven't benchmarked the team laptop yet; `scripts/benchmark_hybrid.py` does that. |
| **Does it scale to 100 TB?** | Not demonstrated. The design is one CPU worker per clip, with observations cached once and the quality pass re-run from cache (8 s for a 30 s clip). It's untested at scale. |
| **What's the industrial benefit?** | A working review workflow on real footage: jump to failures, confirm events, export only usable segments. We haven't measured the time saved; the pilot protocol is ready. *(If you ran the pilot, give the result with n.)* |
| **Privacy?** | Everything runs locally, the server binds to localhost, and footage and outputs are git-ignored with a pre-commit hook and a history check. Each run records consent and retention fields; these are operator statements, not verified compliance. Our face-flag experiment wasn't good enough to ship. |
