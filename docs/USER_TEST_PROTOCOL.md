# User tests: protocol (NOT yet run)

Neither test has been run, so there are no results. The protocol is ready to run with 3–5 reviewers.

## 1. Does 3D + timeline beat plain video?

**Setup**
- **Clip:** 60–150 s of `mytronlabs-000060-016` (processed run available).
- **Questions** (answer key from the labelled frames and the run):
  1. At what time does the right hand first leave the view after 62 s?
  2. When does it come back?
  3. Which hand holds the cloth at 100 s?
  4. Find a stretch of at least 1 s where the left hand barely moves.

**Conditions** (counterbalanced, a different clip interval per condition):
- **A.** Plain video player.
- **B.** EgoHand Twin Review workspace.

**Measures:** time per question, correctness, missed events and confidence (1–5). **Report** the sample size, per-person results and no averages beyond the sample.

## 2. Review-time pilot

- **Task:** list every tracking failure and reacquisition in a 30 s interval.
- **A.** By scrubbing the video. **B.** With the timeline (F / R keys, events strip).
- **Measures:** time to completion and recall of the events (ground truth: the run's events, checked by a second person).
- **Limits:** tiny sample; reviewers learn the clip; the tool shows its own events, which could bias B. Rotate intervals between conditions.
