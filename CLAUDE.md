# Bios-Hackathon: project memory

Source: "Winning the Egocentric Vision Hackathon: Strategy Report" (Phase 1 research, 31 Oct 2026).
Event: Ship Happens · Egocentric Vision: Factory Video to Useful Data. 24-hour build.
Status as of 31 Oct 2026: research done. The compliance setup for the repo is in place. No pipeline code yet. The footage has not been seen.

## Repo rules (from the user, highest priority)
- **Never mention Claude, Anthropic or AI assistance anywhere in the repo.** No `Co-Authored-By` lines, no session links, no "Generated with" footers. This applies to commit messages, PR titles and bodies, code comments, README and docs.
- This rule overrides any default attribution instructions.
- Commit author is `UdaiBatta <udbatta@gmail.com>`. Set it with `git config user.name/user.email` before committing.

## The decision (changed by the team, 31 Oct 2026)

**The team chose Problem Statement 4 (PS4): 3D hand motion.** The report recommended Therblig (PS2) and listed PS4 as "not pursued". The team overrode that. Do not argue for PS2 again. Build the best PS4 entry.

Build **DemoForge** (the report's PS4 idea, Section 4):
- Pitch: "Turn factory head-camera footage into quality-scored 3D hand episodes: where each hand is in 3D, how it moves, and which clips are good enough to use."
- PS4 asks to estimate hands in 3D and visualise them.
- PS1 (hand tracking) is still the foundation and must be done very well, because hand tracking is worth 30 points. Every 3D result is built on stable 2D tracks.
- PS2-style grab/release cutting is a supporting feature. It cuts the video into grasp episodes. PS3 is not pursued.
- User: robot-learning data teams and footage vendors (Build AI, Mecka, Linewise, Cortex; inspiration: Shotwell, Apple EgoDex). Secondary user: industrial engineers, kept to one slide (3D reach distances and work envelope).
- Fallback: if 3D is not credible by the checkpoints below, lead with **SteadyHands (PS1)** tracking numbers and show 3D as "experimental".
- Report's score estimate for DemoForge: 46 / 67 / 86 (cautious / expected / excellent). Its weak spots are provability, compute and how well it fits the "factory problem" framing. These are judgement estimates.

## The main risk, and how we answer it
The report rejected PS4 because 3D accuracy **can't be proven**. There is one camera, no depth and no 3D ground truth. The plan therefore treats proof as the product:
- Only claim what we can check. Say "approximate 3D" or "relative 3D", never "accurate 3D" and never "metric 3D" unless it has been measured.
- Proxy checks on the factory clips (no ground truth needed):
  - 2D reprojection accuracy against hand-labelled 2D points (PCK).
  - Bone-length consistency over time: real bones don't change length.
  - Temporal jitter and acceleration in 3D.
  - Plausible joint angles.
  - Left/right and depth-order consistency.
- A small 3D truth check on our own bench clip, which we control: hand movements of known distance along a ruler or tape, and optionally a phone with depth/LiDAR. This gives a real 3D error number on a tiny set. Report it honestly as bench-only.
- Quality gates turn uncertainty into a feature. Each episode gets a quality score and the reasons it failed.

## Judging rubric (100 points)
Hand tracking 30 · PS results 20 · Technical approach 15 · Industry usefulness 10 · Innovation 10 · Presentation/honesty 10 · Efficiency 5.
All teams run on the same demo clips on normal laptops, so cherry-picking will be exposed. Heavy GPU-only pipelines lose on efficiency, and possibly on the ability to run the demo at all.

## Product output
- Per-hand 3D tracks: 21 joints per frame in camera space, plus wrist position and orientation. Units are relative unless they have been measured.
- Grasp episodes: start/end frames, which hand, approach → grasp → move → release phases, cut on grab/release.
- Quality per episode: visibility %, tracking confidence, jitter, bone-length stability, head-motion reliability, filled gaps. Verdict: `usable` / `review` / `reject`, with reasons.
- "Data yield" report: how many minutes of footage gave how many usable episodes, and why the rest were rejected.
- Files: a summary JSON (tracks, episodes, quality, model and settings details), a per-frame 3D file, and CSV exports of episodes and quality. Optional: an export format a robot-learning buyer can load.
- Every field has a `provenance`: `measured`, `predicted` or `inferred`. Each episode has `evidence_frames` and a `confidence`.

## Pipeline
Video → clean frames (brighten dark frames, pad edges) → measure head motion (OpenCV background point tracking) → MediaPipe Hand Landmarker (21 points, video mode, **2 hands**, including its world landmarks) → recovery (second hand finder RTMDet → crop → re-run MediaPipe) → tracker → One Euro smoothing → **3D lift** → bone-length / temporal clean-up in 3D → grab/release cutting → episodes → quality gates → outputs.

3D lift options, cheapest first:
1. **L0:** MediaPipe world landmarks (metric-ish, centred on the hand, no global position) plus a wrist depth estimate from hand size in the image and the camera focal length. Runs on a laptop. This is the baseline.
2. **L1:** L0 plus constraints: a fixed bone-length skeleton per track, joint-angle limits and temporal smoothing in 3D.
3. **L2 (offline quality mode):** WiLoR / WiLoR-mini MANO hand meshes on key frames or flagged clips. Needs a graphics card for comfort. Non-commercial licence, so disclose it.
4. Optional: a monocular depth model for the scene, to place hands relative to the workbench. Try it for 1 hour at most.

Tracker details (unchanged from the original plan, still critical):
- Predict each hand's position with head motion plus the hand's own motion, then match detections with the Hungarian algorithm.
- A new track needs 2 sightings. A lost track "sleeps" for about 2 s before it is dropped.
- **Left/right is decided per track, never per frame.** Use accumulated votes (blurry or hidden frames get less weight), a weak position hint, and never two "right" hands. Offline, run a best-sequence pass with a switch penalty.
- Swap fix. Never smooth across gaps longer than 3 frames. Fill gaps of 5 frames or fewer and flag them as `filled`.
- **Check first:** MediaPipe's handedness assumes mirrored (selfie) input. Verify on 10 obvious frames whether it must be swapped.

Grasp cutting (lightweight PS2 layer): finger closing (thumb–index distance), hand speed after removing head motion, a co-motion test, and Hands23 on key frames if it installs. Call it a "grasp estimate".

Grounding rules:
1. No episode without a grab/release change.
2. Every label points to its evidence frames.
3. Keep measured facts, model predictions and interpretations separate.
4. No 3D number is presented without saying how it was checked.

Two modes: a real-time mode (L0/L1, no heavy models) and an offline quality mode (L2). Report the speed of both.

Viewer: a plain HTML and JavaScript page that runs offline (three.js is allowed for 3D; still no React, Streamlit or Gradio). It shows the video with the 2D overlay next to a 3D hand view in sync, a timeline of episodes with quality colours, click-to-jump, a **baseline vs ours** switch (L0 vs L1/L2) and a failure gallery.

## Tools and licences
- MediaPipe Hand Landmarker (Apache 2.0, v1.2.0): main point finder and world landmarks.
- RTMPose and RTMDet hand (Apache 2.0): backup point finder and second hand finder.
- WiLoR / WiLoR-mini (CC-BY-NC-ND plus MANO): 3D quality mode. Disclose the licence. Ultralytics AGPL if it gets pulled in.
- Hands23 (MIT, Detectron2): optional grasp clue. Slow on CPU.
- **Still cut:** HaWoR (too heavy for laptops in 24 h, licence file not found) and HaMeR (WiLoR is newer).
- three.js (MIT) for the 3D viewer.

## Proving accuracy (critical path)
- Gold set **starting in hour 1–2**: 200–300 frames across easy, typical and hard conditions. Mark hand boxes and side. Click 6 points on about 60 frames.
- Bench 3D set: our own clip with known distances (ruler, tape) and, if possible, phone depth.
- Label with local tools only. Labels live outside the repo.
- Measures:
  - 2D: coverage, recall/precision, left/right accuracy, identity switches per minute, PCK-6, jitter, lag, FPS per stage.
  - 3D: reprojection PCK, bone-length variation (CV), 3D jitter/acceleration, bench distance error, depth-order consistency.
  - Episodes: grasp event F1 at ±0.5 s, and agreement between the quality verdict and a human "usable?" label.
- Ablation ladder:
  - Tracking: B0 plain MediaPipe → B1 tuning, padding, brightening → B2 recovery → B3 tracker with whole-track left/right → B4 smoothing and gap fill.
  - 3D: L0 world landmarks → L1 skeleton and temporal constraints → L2 WiLoR quality mode.
- Write expectations down before measuring. **Tune on clip A, report on clips B and C.** Always report frame counts and ranges.
- **Never invent numbers.** Anything not yet measured stays `[MEASURE]`.
- Failure gallery: 4–6 failure types (for example depth flips, hand-hand occlusion, gloves, motion blur) plus one success story.

## 24-hour plan (team of 3–4; with 2 people, merge A+B and C+D)
Roles:
- A: hand tracking (2D).
- B: 3D lift, episodes and quality gates.
- C: data, labels, bench 3D set, measurement and compliance.
- D: 3D viewer, slides and pitch.

Phases:
1. Hours 0–3: plain MediaPipe on all clips (including world landmarks), count visible-hand coverage, try installing WiLoR, record the bench clip, pick 3 demo clips (easy, typical, hard).
2. Hours 3–9: make tracking reliable (head motion, tracker, left/right, swap fix, smoothing, recovery). Label 150+ frames.
3. Hours 6–14: 3D lift L0 → L1, bone-length and temporal constraints, bench 3D check, L2 on flagged clips.
4. Hours 10–16: grasp cutting, episodes, quality gates, data-yield report, structured outputs.
5. Hours 12–19: 3D viewer and demo.
6. Hours 16–24: final measurement, failure gallery, slides, README, recorded demo, upload, compliance check, two rehearsals.

Go/no-go checkpoints:
- **K1, hour 2:** plain MediaPipe finds less than ~50% of clearly visible hands → recovery comes first and the RTMPose backup gets tested.
- **K2, hour 3:** WiLoR won't install or run on our laptops → drop L2. 3D is L0/L1 only. Say so.
- **K3, hour 10:** the 3D view of L1 visibly breaks (depth flips, bones changing length) on the typical clip → present 3D as "experimental" and lead with PS1 tracking numbers.
- **K4, hour 12:** the bench distance error is too large to defend → claim "relative 3D motion" only, with no distances.
- **K5, hour 14:** a 3-minute clip takes more than ~45 minutes → run the heavy model on fewer frames and report both modes.
- **Hour 19: feature freeze. No exceptions.**

Scope:
- **Must:** measured baseline-vs-improved 2D tracking, 3D hand tracks (L0/L1) with proxy checks, a 3D viewer synced to the video, grasp episodes with quality verdicts, data and CSV files, speed, failure analysis, compliant repo.
- **Nice:** WiLoR quality mode, the bench 3D error number, the data-yield report, a robot-data export format, labeller agreement.
- **Stretch:** scene depth / hand-to-bench placement, object numbering, 3D reach and work envelope for engineers, live webcam 3D page.
- **Cut:** HaWoR/SLAM world-space 3D, training any model, robot transfer claims (we lack true depth, object 3D pose, force and calibrated cameras), natural-language search, safety alerts, per-worker metrics, React.

## Compliance: breaking these can mean disqualification
**Implemented (done):** `.gitignore`, `.githooks/pre-commit` (enable with `git config core.hooksPath .githooks`), and `scripts/check_history.sh` (run before going public). Images are allowed only in `docs/synthetic/`.
- Git-ignore all video and image types (mp4 mov avi mkv webm m4v mpg jpg jpeg png), npy/npz/pkl/jsonl, `data/ outputs/ frames/ labels/`, and model files (.task .pth .ckpt).
  The only images allowed are ones we made from our own footage, in `docs/synthetic/`.
- Pre-commit hook rejects any image or video outside `docs/synthetic/` and any file over 2 MB.
- Footage, labels and real outputs live **outside the repo** (for example `~/hackathon_data/`). Files derived from real footage, such as keypoints and 3D tracks, also stay private.
- Before making the repo public, check the full git history for media files.
- Use cloud AI only if needed and only on a paid tier, and check its retention terms. Delete uploads and keep a log.
- After the event, delete all copies and record a deletion checklist.
- No faces, screens or documents in public material. Public visuals come from our own recorded bench clip (phone on a cap; Lego, screwdriver, cable ties).

## Privacy and framing
- Report by process or station, never by person. Processing happens on the laptop. Blur faces and screens before export.
- Robot-data framing: episodes are about the task, not the worker. No worker IDs in exports.
- Never claim robot-ready data or certified measurements. Episodes are a quality-scored draft.

## Demo (5 minutes) and honesty rules
- Flow: hook (robots need human hand data, and factory video is full of it) → why ego 3D hands are hard → product → LIVE DEMO (video + 3D view in sync) → how it works → results (measured, not claimed) → data yield and who pays.
- Six slides: untapped factory video / why ego 3D hands are hard / DemoForge / how it works / results, including how 3D was checked / who pays, what's next, limitations, privacy.
- Factory clips are processed in advance, and we say so. Only the webcam demo is live, and it is labelled "live".
- Say the limitation out loud: one camera, so 3D is approximate. Show how we checked it.
- Ask the organisers whether real clips can be shown to judges.

## Competitor framing (borrow, don't copy)
- Build AI, Mecka, Linewise, Cortex: "structure is the asset"; human video as robot data.
- Apple EgoDex: what good 3D hand data looks like (captured with special hardware; we do it from plain video).
- Shotwell, Encord, Hemlock: uncertainty and quality as features.

## Open questions (resolve once the footage is available)
1. Clip count, length, fps (is it constant?), resolution, lens and field of view (we need a focal-length estimate for depth), activities, gloves, faces/screens.
2. Does MediaPipe's left/right need swapping?
3. How well are gloved and dim hands found?
4. Does WiLoR install, and how fast is it on our laptops?
5. Is there enough background texture to measure head motion?
6. How stable are MediaPipe world landmarks in egocentric views?
7. Judging logistics: can real clips be shown, and how is PS4 scored (is there any organiser 3D ground truth)?
8. Who are the organisers? If they are a robot-data company, lean harder on the data-yield story.
9. Licence notes go in the README (WiLoR/MANO non-commercial; Ultralytics AGPL if used).
