# Final submission plan: prompts to close every gap

**Goal.** Close the gaps against the judging criteria and the three submission items:
- a public repository without the footage;
- processed demo clips in the private Drive folder;
- 5–6 slides.

Then rehearse a 5-minute demo with 3 minutes of questions.

**How to use this file.**
- Run the prompts **in order**. Each one stands alone: paste the **Shared rules** block first, then the prompt.
- Steps marked **HUMAN** need a person.
- Every prompt ends with **Done when**. Do not start the next phase until it holds.

| Phase | Prompt | Criterion it serves | Owner | Time |
| --- | --- | --- | --- | --- |
| 0 | Decide: how the repository goes public | Submission | **HUMAN** (team lead) | 10 min |
| 1 | P1 Bug bash: no visible errors in the demo path | Presentation, results | agent | 45 min |
| 2 | P2 Documentation truth pass | Presentation and honesty | agent | 30 min |
| 3 | P3 Run every preset on the common demo clips | Accuracy (30) | agent | 60–90 min (mostly compute) |
| 4 | P4 Label frames of the common clips | Accuracy (30) | **HUMAN** + agent | 60 min |
| 5 | P5 Review the existing labels, re-score | Accuracy (30), honesty | **HUMAN** + agent | 45 min |
| 6 | P6 Laptop benchmark | Efficiency (5) | agent on the laptop | 15 min |
| 7 | P7 Processed demo clips for the Drive folder | Submission, results | agent; **HUMAN** uploads | 30 min |
| 8 | P8 Review-time pilot (optional, high value) | Usefulness (10) | **HUMAN** ×2–3 + agent | 30 min |
| 9 | P9 Slides (5–6) | Presentation (10) | agent; **HUMAN** checks | 45 min |
| 10 | P10 Public repository copy | Submission | agent; **HUMAN** publishes | 30 min |
| 11 | P11 Demo hardening and backup video | Presentation | agent + **HUMAN** | 40 min |
| 12 | P12 Final gate and merge to main | All | agent | 20 min |
| 13 | P13 Q&A rehearsal | Presentation and honesty | **HUMAN** + agent | 20 min |

Phases 3–4, 6–8 and 9 can run in parallel on different machines. Phase 10 must come after phase 2, and phase 12 comes last.

---

## Shared rules (paste at the top of every prompt)

```text
Project: EgoHand Twin, repo UdaiBatta/BIOS---Ship-Happens, branch udai-s1 (work there; never push to main
unless the prompt says so; never force-push; never rewrite history).
Rules that always apply:
- Private footage and everything derived from it (videos, frames, screenshots of real footage, JSONL/CSV/NPZ, runs/,
  data/, labels, models) never goes into git, slides, public material or any new online service. media/, data/,
  runs/, models/ are git-ignored; keep them that way. Screenshots of the viewer may only show the synthetic demo.
- Commits are authored "UdaiBatta <udbatta@gmail.com>". No co-author lines, no tool or AI attribution anywhere
  (commits, PR text, code, docs).
- Labels are provisional until a person reviews them; never set reviewed=true yourself.
- Every number you write must come from a command you ran in this session; give denominators ("39 of 78").
  If something was not measured, say "not measured".
- The backend binds to 127.0.0.1 only. Do not change repository visibility.
- Run the tests before every commit: `uv run pytest -q` and `cd backend && uv run python manage.py test`.
```

---

## Phase 0 · HUMAN decision: how the repository goes public

The repository is private, and the release `ps4-baseline-handoff-20261031` holds `ps4-source-video.zip` (the private footage). Making this repository public would publish that zip. Several docs also name clips and describe footage (`docs/SUBMISSION.md` lists them). Pick one option:

- **A (recommended): a new public repository** holding a clean snapshot of `main`. It has no releases, no old history and no internal docs. The private repository stays as it is. See P10.
- **B: make this repository public** after deleting the footage release asset and removing the internal docs. This is riskier: old commits and release pages stay visible, so everything must be checked first.

Write the choice and the public repository name here before running P10.

---

## P1 · Bug bash: no visible errors in the demo path

```text
Goal: the demo path works with no errors, warnings or confusing states on a fresh start.
1. Start the backend and worker with scripts/run_local.sh (Linux/macOS) or read scripts/run_local.ps1 for Windows logic.
2. With Playwright (Chromium is pre-installed; do not reinstall it), drive http://127.0.0.1:8000/ and record every page
   error, console error and failed request while you:
   a. open the page; check it shows the selected video (newest run or a preview frame), not the synthetic demo;
   b. switch Review / Analysis / Diagnostics workspaces and every split preset;
   c. for each preset the server offers, process a 5 s segment of a registered video and load the result;
   d. in the 3D panel try Skeleton / Mesh / Mesh + skeleton, Side / Top / Camera, follow hands on/off, Raw/Smoothed,
      wheel zoom, Reset view;
   e. use the timeline: click, drag, zoom, F (next failure), R (next reacquisition), the events list, Confirm/Reject an event;
   f. error paths: worker stopped (run must say "still queued: is the worker running?"), an unprocessed video, a missing
      video file (rename one temporarily, then restore it), upload of a small mp4.
3. Fix every defect you can reproduce, with the smallest change. Add a regression test where a test is possible.
4. Write docs/BUG_BASH.md: each check, pass/fail, what was fixed (commit hash). No screenshots of real footage.
Done when: every check passes, both test suites pass, BUG_BASH.md is committed and pushed to udai-s1.
```

## P2 · Documentation truth pass

```text
Goal: nothing in the repository contradicts the code or the measured numbers.
1. Re-run the test suites and record the counts.
2. Read README.md, frontend/README.md, docs/SUBMISSION.md, docs/DEMO_SCRIPT.md, docs/IMPLEMENTATION_SUMMARY.md,
   docs/PERFORMANCE_REPORT.md, docs/KNOWN_LIMITATIONS.md, docs/TODO.md, docs/EXPERIMENTAL_3D_STATUS.md. Fix at least:
   - test counts (pipeline and backend);
   - PERFORMANCE_REPORT "Smoothing" section still describes the old One Euro wrist filter; the shipped smoother is the
     forward-backward Kalman (RTS) wrist + One Euro fingers (see src/egohand_twin/smoothing.py and SMOOTHING_COMPARISON.md);
   - README status table: bone-length calibration done, motion events done (heuristic), privacy flags experimental;
   - mesh size: 970 vertices / 1,872 triangles;
   - the 3D panel changes (Side/Top/Camera, follow hands, camera-space smoothing, depth cues) and the FFmpeg lookup
     (EGOHAND_FFMPEG_DIR) in README and DEMO_SCRIPT;
   - DEMO_SCRIPT's demo steps must match the current viewer (video selection auto-loads the newest run).
3. Add a short "Results at a glance" section at the top of README.md: the accuracy table per preset with
   denominators and the word "provisional" until phase 5 is done, speed, and the honest limits.
4. grep the docs for numbers that appear in more than one place and make them agree.
Done when: a reader can follow README from clone to demo without hitting a wrong statement; committed and pushed.
```

## P3 · Run every preset on the common demo clips

The brief says: "Hand-tracking accuracy is evaluated for every option. Show results on the common demo clips." Today we have numbers on one clip only.

```text
Goal: per-clip, per-preset results on the organisers' common demo clips.
Inputs (fill in): COMMON CLIPS = <paths under media/, e.g. media/Sample/...>; they stay local.
1. For each clip and each preset (baseline, recall, accurate, and hybrid if the RTM models are installed), run
   `uv run egohand process <clip> --out runs/common/<clip>/<preset> --preset <preset> --no-video` (whole clip, or the
   same fixed interval for all presets if a clip is over 3 min; record the interval).
2. Without labels, compute per run from landmarks.jsonl / metrics.json: frames, fraction of frames with an observed
   wearer hand, hands per frame, left/right/unknown share, left-right flips inside tracks, predicted (2D-only)
   share, fraction lifted to camera-space 3D, processing seconds and frames per second. Call them coverage and
   stability, never accuracy.
3. Write scripts/evaluate_common_clips.py that does steps 1–2 reproducibly and writes runs/common/summary.json (private).
4. Write docs/COMMON_CLIPS_RESULTS.md: one table per clip (rows = presets), plus a pooled table. Name clips by a neutral
   id (C1, C2, ...), not by file name. Say plainly which numbers are coverage and which are accuracy.
5. Keep the runs: phase 4 uses them; phase 7 renders from them.
Done when: the table exists for every common clip and every preset; the script reproduces it; committed and pushed.
```

## P4 · Label frames of the common clips (HUMAN + agent)

```text
Goal: real accuracy numbers on the common clips (recall, precision, F1, wrong-side rate per preset).
1. For each common clip build an annotation set of about 30 frames spread over the clip:
   `uv run egohand annotation-set <clip> --out data/private/labels_common/<id> --intervals <a:b,...> --split holdout`
   (read `egohand annotation-set --help` and the label format in src/egohand_twin first; reuse the existing format).
2. HUMAN: label every visible wearer hand (wrist position, side, visible/occluded) in those frames using the generated
   sheets. Two people label 10 shared frames each so agreement can be reported.
3. Agent: validate the label files, then score every preset run from P3 with `uv run egohand evaluate ... --summary`
   (same matching rule as RESULTS_V2: one-to-one within 0.10 of the image diagonal). Report agreement between the two
   labellers on the shared frames.
4. Add the accuracy tables to docs/COMMON_CLIPS_RESULTS.md and README "Results at a glance".
Done when: every preset has recall/precision/F1/wrong-side numbers with denominators on every common clip.
```

## P5 · Review the existing labels and re-score (HUMAN + agent)

```text
Goal: replace "provisional" with "reviewed" for the dev/holdout numbers.
1. Run `uv run egohand label-review` (see docs/SUBMISSION.md) to create data/private/label_review/review.csv.
2. HUMAN: a teammate who did not make the labels fills review.csv (about 45 min).
3. Agent: `uv run egohand label-review-apply ...`, then re-run every evaluation command in docs/RESULTS_V2.md §8 and the
   tables in HANDEDNESS_ROOT_CAUSE.md, SMOOTHING_COMPARISON.md and EXPERIMENT_RESULTS.md. Update the numbers
   everywhere (README, DEMO_SCRIPT, slides). If a number got worse, report it as it is.
Done when: no doc says "provisional" for figures that were reviewed; the change log lists every number that moved.
```

## P6 · Laptop benchmark (agent on the team laptop)

```text
Goal: speed figures from the presentation laptop (Windows 11, RTX 4060 Laptop, Ryzen 7 7840HS, 16 GB).
1. In D:\BIOS on branch udai-s1, close other heavy apps, plug in power, then run
   `uv run python scripts/benchmark_hybrid.py` (read its --help first) for baseline, recall, accurate (and hybrid if installed)
   on the same 30 s interval as docs/PERFORMANCE_REPORT.md.
2. Also time one backend run end to end from Process to "run loaded" in the viewer.
3. Add a "Team laptop" table to docs/PERFORMANCE_REPORT.md next to the cloud-VM table; keep both, labelled.
Done when: the laptop table is committed and the slides use laptop numbers.
```

## P7 · Processed demo clips for the Drive folder (agent; HUMAN uploads)

```text
Goal: one processed MP4 per common clip, ready for the organisers' private Drive folder.
1. For each common clip, use the best preset from P3/P4 (accurate unless results say otherwise) and render the
   overlay video: re-run `egohand process` WITHOUT --no-video (or `egohand replay`), output to
   deliverables/drive/<clip-id>_<preset>.mp4 (git-ignored: add deliverables/ to .gitignore first).
2. Each video must show: 2D skeletons with Left/Right/unknown colours, track ids, a small banner with clip id, preset,
   and "provisional labels / estimated depth" as applicable. Check every file plays (ffprobe duration > 0, H.264, yuv420p).
3. Write deliverables/drive/README.txt: what each file is, preset, interval, and the measured numbers for that clip.
4. Do NOT upload anything. List the files and sizes for the human.
HUMAN: upload deliverables/drive/* into the designated private Drive folder only.
Done when: every common clip has a playable processed MP4 and the human confirms the upload.
```

## P8 · Review-time pilot (optional, best evidence for "usefulness to industry")

```text
Goal: a small measured result instead of "not measured".
Follow docs/USER_TEST_PROTOCOL.md §2 with 2–3 participants on a 30 s interval: time to find every tracking failure
(a) by scrubbing the raw video and (b) with the viewer timeline (F / R keys, events list). Record times and the
failures found in data/private/pilot/*.csv. Report medians with n, and say this is a pilot, not a study.
Add the result to docs/USER_TEST_PROTOCOL.md (results section), README and the slides.
Done when: the pilot table is committed.
```

## P9 · Slides (5–6)

```text
Goal: a 6-slide deck that frames the live demo. Build it as slides/EgoHand_Twin.pptx (python-pptx; the pptx skill if
available). No footage frames: diagrams, tables, and screenshots of the SYNTHETIC demo only.
Use the plan in docs/DEMO_SCRIPT.md §2 with the numbers from P3–P8:
1. Problem and user: factory video → 3D hand motion people can trust.
2. What we built: pipeline diagram (video → detection presets → tracking with explicit states → smoothing →
   3D lift → viewer/timeline/exports), one line each.
3. Live demo cue slide (what to watch for).
4. Accuracy: per-preset table on the common clips (recall, precision, F1, wrong side) with denominators; the rejected
   hybrid with its rule.
5. Efficiency and usefulness: laptop speed, review-time pilot, quality windows and exports.
6. Honest limits and next steps: assumed lens, no fitted mesh, no camera-motion compensation, label status.
Keep each slide under 40 words of body text; large numbers; consistent colours (left orange, right blue).
Export a PDF copy too. Check every number against the docs.
Done when: the deck opens, every number has a source in the docs, and a teammate has read it end to end.
```

## P10 · Public repository copy (after phase 0 decision and P2)

```text
Goal: a public repository without footage, derived data, models or internal notes.
For option A (new public repository, recommended):
1. Export the tree of origin/main (git archive) into a new folder; do not copy .git.
2. Remove: docs that name clips or describe the footage (the list in docs/SUBMISSION.md, plus
   AGENT_CONTINUATION_PROMPT.md, REFERENCE_ARTIFACTS.md, FINAL_SUBMISSION_PLAN.md), anything under media/, data/,
   runs/, models/, deliverables/, slides/ sources with real data, and the private-release download step in
   scripts/run_local.* (replace it with "put your own videos in media/").
3. Scan the copy: file types (no video, image of footage, npz/jsonl/csv of runs, tflite/onnx), file sizes > 5 MB,
   strings: clip ids, "data/private", release names, tokens, e-mail addresses other than the author's.
   Run scripts/check_history.sh against it.
4. Verify it still works from scratch: fresh clone into a temp dir, `uv sync`, both test suites, run_local with a
   synthetic or public test video.
5. Initialise a new git repository with one commit by UdaiBatta, and hand the folder to the HUMAN.
HUMAN: create the public GitHub repository and push it; add the link to the slides and the submission form.
Done when: the public repo clones and tests pass, and the scan finds nothing.
```

## P11 · Demo hardening and backup video

```text
Goal: the live demo cannot fail on stage.
1. Write scripts/preflight.ps1 (Windows) and scripts/preflight.sh: checks ffmpeg/ffprobe found, server answers
   /api/health, worker running, the prepared demo run exists and loads, disk space, battery/power plan note.
   Print one PASS/FAIL line per check.
2. Prepare the demo runs on the laptop in advance (the intervals named in docs/DEMO_SCRIPT.md, preset accurate), so
   nothing is processed live except an optional 5 s segment.
3. HUMAN: record a 5-minute screen capture of the full demo script as a backup (kept private, on a USB stick, not in git).
4. Update docs/DEMO_SCRIPT.md: exact click path, which run to load, fallback ladder (no network needed; backup video;
   synthetic demo as the last resort, clearly labelled).
Done when: preflight passes twice on the laptop from a cold start and the backup video plays.
```

## P12 · Final gate and merge to main

```text
Goal: main = the presented version.
1. On udai-s1: both test suites pass, scripts/check_history.sh is clean, the P1 bug bash passes again,
   git status is clean, no file over 5 MB is tracked.
2. Open a PR udai-s1 → main with a plain description of what changed (no attribution lines), merge with a merge
   commit (not squash) after the HUMAN approves.
3. On the laptop: git checkout main, git pull, preflight passes.
Done when: main is merged, the laptop runs main, preflight passes.
```

## P13 · Q&A rehearsal (HUMAN + agent)

```text
Act as a strict judge for this project. Using README.md, docs/DEMO_SCRIPT.md §5 and docs/COMMON_CLIPS_RESULTS.md,
ask 12 hard questions one at a time (accuracy on unseen clips, depth validity, why not MANO/WiLoR, left/right errors,
failure cases, speed, privacy, what is novel, how a factory would use it, what you would do with one more week).
After each answer, score it 1–5 for correctness and honesty and give a better 30-second answer that uses only
measured numbers with denominators. End with the 5 answers that need the most practice.
Done when: every presenter can answer the top 10 in under 30 seconds.
```

---

## Definition of "presentable"

- [ ] The demo path has no visible errors (P1), and the docs match the code (P2).
- [ ] Every preset has accuracy numbers with denominators on the common demo clips (P3, P4). Reviewed labels where possible (P5).
- [ ] Laptop speed numbers (P6), and processed clips uploaded to Drive (P7).
- [ ] 6 slides, every number traceable (P9).
- [ ] The public repository contains no footage, derived data or internal notes, and it clones and passes its tests (P10).
- [ ] Preflight passes, a backup video exists, `main` is the presented version (P11, P12).
- [ ] Q&A rehearsed (P13).
