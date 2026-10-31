# Bios-Hackathon: project memory

Source: "Winning the Egocentric Vision Hackathon: Strategy Report" (Phase 1 research, 31 Oct 2026).
Event: Ship Happens · Egocentric Vision: Factory Video to Useful Data. 24-hour build.
Status as of 31 Oct 2026: research and planning only. No code yet. The footage has not been seen.

## The decision

Build **Therblig** and enter it under **Problem Statement 2 (PS2): what is the hand touching?**
- PS1 (hand tracking) is the foundation and must be done very well. PS3 (step timeline) is a supporting feature.
- PS4 (3D hands) is not pursued because its accuracy can't be proven. PS5 (open innovation) is used only for the factory story.
- Pitch: "Automatic motion study from a head camera: what each hand touched, for how long, and where the workstation wastes hand motion. Every number links to the frame that proves it."
- User: industrial or improvement engineer (time-and-motion study). Second market, kept to one closing slide: robot-learning data buyers (Build AI, Mecka, Linewise, Cortex).
- Runner-up and fallback: **SteadyHands (PS1)**. It is literally the first half of Therblig.
- Wildcard: DemoForge (PS4, robot episodes). Only its "data yield" report survives, as a 30-second closing slide.
- Expected score: ~72–74/100, range 55–90. These are judgement estimates.

## Judging rubric (100 points)
Hand tracking 30 · PS results 20 · Technical approach 15 · Industry usefulness 10 · Innovation 10 · Presentation/honesty 10 · Efficiency 5.
All teams run on the same demo clips on normal laptops, so cherry-picking will be exposed.

## Product output
- Two-lane timeline, one lane per hand. States: no contact / holding a loose (portable) object / touching a fixed surface / holding still ("clamp", purple) / uncertain. Grab and release markers. Clicking a point jumps the video to that frame.
- Basic motions (therbligs): Reach, Grab, Move, Hold (holding a portable object with almost no movement for more than 1 s, the "clamp signal"), Position/use, Release, Idle (no contact and no movement for more than 1 s).
- Motion-economy audit (Barnes): % of time both hands are idle, % of time one hand holds something still (a fixture opportunity), and hand imbalance.
- Files: a summary JSON (tracks, segments, events, objects, motions, audit, quality, model and settings details), a per-frame file, and CSV exports of events and segments.
- Every field has a `provenance`: `measured`, `predicted` or `inferred`. Each event has `evidence_frames` and a `confidence`.

## Pipeline
Video → clean frames (brighten dark frames, pad edges) → measure head motion (OpenCV background point tracking) → MediaPipe Hand Landmarker (21 points, video mode, **2 hands**) → recovery (second hand finder RTMDet/Hands23 → crop → re-run MediaPipe) → tracker → One Euro smoothing → contact detector (Hands23 on key frames, ~3 fps) → co-motion test → sticky HMM → events and motions → outputs.

Tracker details:
- Predict each hand's position with head motion plus the hand's own motion, then match detections with the Hungarian algorithm.
- A new track needs 2 sightings. A lost track "sleeps" for about 2 s before it is dropped.
- **Left/right is decided per track, never per frame.** Use accumulated votes (blurry or hidden frames get less weight), a weak position hint, and never two "right" hands. Offline, run a best-sequence pass with a switch penalty.
- Swap fix. Never smooth across gaps longer than 3 frames. Fill gaps of 5 frames or fewer and flag them as `filled`.
- **Check first:** MediaPipe's handedness assumes mirrored (selfie) input. Verify on 10 obvious frames whether it must be swapped.

Contact (the core of PS2):
- Clues: Hands23 contact state and object box, finger closing (thumb–index distance), hand speed after removing head motion, co-motion, overlap.
- **Co-motion test:** after removing head motion, a portable object moves with the hand and a fixed surface moves with the background. A still hold stays undecided until the object moves.
- HMM per hand with states none / portable / fixed. It is sticky, and a contact must last at least 0.2 s. Use Viterbi offline and a delay buffer in real time.
- **Re-label the past:** if an object labelled "fixed" later moves, the whole contact becomes portable.
- Use an explicit `uncertain` state when clues disagree, the frame is blurry, or head motion is unreliable.
- Known limitation, said openly: a loose part pressed down and never moved looks "fixed".
- Wording: call it a "contact estimate", never "contact detection".

Four grounding rules:
1. No event without a contact change.
2. Every label points to its evidence frames.
3. AI may only *name* existing steps from a fixed list (allowing "unknown"). It never creates steps.
4. Keep measured facts, model predictions and interpretations separate.

Two modes: a real-time mode without the heavy detector and offline clean-up, and an accurate offline mode. Report the speed of both.

Viewer: a plain HTML and JavaScript page that runs offline. Not Streamlit/Gradio, not React. It shows the video with an overlay (raw/smoothed toggle), the two-lane timeline, a motions bar, audit numbers that highlight their evidence, an event list with click-to-jump, a **baseline vs ours** switch and a failure gallery. Optional: live webcam page.

## Tools and licences
- MediaPipe Hand Landmarker (Apache 2.0, v1.2.0): main point finder.
- RTMPose and RTMDet hand (Apache 2.0): backup point finder and second hand finder.
- Hands23 (MIT, Detectron2): contact detector. Slow on CPU.
- 100DOH (MIT): optional. Try it for 1 hour at most.
- WiLoR (CC-BY-NC-ND plus MANO): optional offline stretch. Disclose the licence.
- **Cut:** HaWoR, HaMeR.
- Stretch object identity: CLIP/DINOv2 fingerprints → "object #k". SAM 2 (Apache) for outlines. SAM 3 has its own licence, so read it first.

## Proving accuracy (critical path)
- Gold set **starting in hour 1–2**: 200–300 frames across easy, typical and hard conditions. Mark hand boxes, side and contact (none/portable/fixed/can't tell).
- Click 6 points on about 60 frames. Mark events on 2–3 clips (3–5 minutes of video). Have 2 people label the same 50 frames to check agreement.
- Label with local tools only. Labels live outside the repo.
- Measures: coverage (not accuracy), recall/precision, left/right accuracy, identity switches per minute, recovery time, PCK-6, jitter, lag, FPS per stage, contact confusion table, balanced F1, event F1 at ±0.5 s and ±0.25 s, timing error.
- Ablation ladder:
  - Tracking: B0 plain MediaPipe → B1 tuning, padding, brightening → B2 recovery → B3 tracker with whole-track left/right → B4 smoothing and gap fill.
  - Contact: C0 Hands23 key frames only → C1 finger and motion clues → C2 co-motion → C3 full HMM with re-labelling.
- Write expectations down before measuring. **Tune on clip A, report on clips B and C.** Always report frame counts and ranges (±5–6 points at about 250 frames).
- **Never invent numbers.** Anything not yet measured stays `[MEASURE]`.
- Failure gallery: 4–6 failure types plus one success story.

## 24-hour plan (team of 3–4; with 2 people, merge A+B and C+D)
Roles:
- A: hand tracking.
- B: contact and events.
- C: data, labels, measurement and compliance.
- D: viewer, slides and pitch.

Phases:
1. Hours 0–3: repo with ignore rules and pre-commit hook (first 20 min), plain MediaPipe on all clips, count the grab rate, try installing Hands23, pick 3 demo clips (easy, typical, hard).
2. Hours 3–9: make tracking reliable (head motion, tracker, left/right, swap fix, smoothing, recovery). Label 150+ frames.
3. Hours 6–14: contact (Hands23, clues, co-motion, HMM, re-labelling, uncertain state).
4. Hours 12–16: structured outputs, motions, audit, annotated video.
5. Hours 12–19: viewer and demo.
6. Hours 16–24: final measurement, failure gallery, slides, README, recorded demo, upload, compliance check, two rehearsals.

Go/no-go checkpoints:
- **K1, hour 1:** fewer than about 3 grabs/releases per minute → switch to PS1 SteadyHands with a light contact layer (or FactoryRecall if the footage is long and varied).
- **K2, hour 3:** plain MediaPipe finds less than ~50% of clearly visible hands → recovery moves first and the RTMPose backup gets tested.
- **K3, hour 7:** Hands23 still produces no output → contact uses finger clues, co-motion and overlap only. Claim "contact events", not object types.
- **K4, hour 12:** three-way contact balanced F1 below ~0.6 on the gold set → two-way (contact / no contact) plus grab/release. Portable vs fixed becomes "experimental". Lead with PS1 numbers.
- **K5, hour 14:** a 3-minute clip takes more than ~45 minutes → run the heavy model on fewer frames and report both modes.
- **K6, hour 16:** audit results flip when thresholds change slightly → ship the timeline only and present the audit as a prototype with a sensitivity table.
- **Hour 19: feature freeze. No exceptions.**
- Any time: AI naming describes things not visible in the frames → drop AI naming.

Scope:
- **Must:** measured baseline-vs-improved tracking, three-way contact timeline with grab/release events and evidence, data and CSV files, viewer with click-to-jump, speed, failure analysis, compliant repo.
- **Nice:** motions and audit, recovery, uncertain state, webcam page, labeller agreement.
- **Stretch:** object numbering, AI naming, cycle detection, ergonomic hints, WiLoR, SAM 2.
- **Cut:** HaWoR/SLAM 3D, 3D meshes, natural-language search, safety alerts, training any model, per-worker metrics, React.

## Compliance: breaking these can mean disqualification
- Git-ignore all video and image types (mp4 mov avi mkv webm m4v mpg jpg jpeg png), npy/npz/pkl/jsonl, `data/ outputs/ frames/ labels/`, and model files (.task .pth .ckpt).
  The only images allowed are ones we made from our own footage, in `docs/synthetic/`.
- Pre-commit hook rejects any image or video outside `docs/synthetic/` and any file over 2 MB.
- Footage, labels and real outputs live **outside the repo** (for example `~/hackathon_data/`). Files derived from real footage, such as keypoints, also stay private.
- Before making the repo public, check the full git history for media files.
- Use cloud AI only if needed and only on a paid tier, and check its retention terms. Delete uploads and keep a log.
- After the event, delete all copies and record a deletion checklist.
- No faces, screens or documents in public material. Public visuals come from our own recorded bench clip (phone on a cap; Lego, screwdriver, cable ties).

## Privacy and framing
- Report by process or station, never by person. Studies are opt-in. Processing happens on the laptop. Blur faces and screens before export.
- Say "fixture opportunity" or "process waste", never "idle worker". Optifye.ai's demo backlash is the cautionary example.
- Lines: "We measure the process to change the workstation, not the person." / "We don't score workers. We show you what their hands are doing — and which workstation is wasting them."
- Never claim certified standard times (MTM/MODAPTS). Timings are a draft that speeds up an engineer's review.

## Demo (5 minutes) and honesty rules
- Flow: Gilbreth hook (15 s) → problem → why it is hard → product → LIVE DEMO → how it works → results → value.
- Six slides: unmeasured process / why ego hands are hard / Therblig / how it works / results (measured, not claimed) / who pays, what's next, limitations, privacy.
- Factory clips are processed in advance, and we say so. Only the webcam demo is live, and it is labelled "live".
- Ask the organisers whether real clips can be shown to judges.

## Competitor framing (borrow, don't copy)
- Retrocausal: engineer vocabulary.
- Drishti (acquired by Apple in 2023): evidence-linked numbers.
- Linewise and Build AI: "structure is the asset".
- Shotwell, Encord, Hemlock: uncertainty and quality as features.
- Cerrion (watch the process) vs Optifye (scored workers, demo pulled).

## Open questions (resolve once the footage is available)
1. Clip count, length, fps (is it constant?), resolution, lens, activities, grab rate, repetition, gloves, faces/screens.
2. Does MediaPipe's left/right need swapping?
3. How well are gloved and dim hands found?
4. Does Hands23 install, and how fast and accurate is it?
5. Is there enough background texture to measure head motion?
6. Does co-motion separate portable from fixed?
7. Are the audit thresholds stable?
8. Judging logistics: can real clips be shown, and is PS2 scored against organiser labels?
9. Who are the organisers? If they are a robot-data company, give the DemoForge slide more weight.
10. Licence notes go in the README (WiLoR/MANO non-commercial; Ultralytics AGPL if used).
