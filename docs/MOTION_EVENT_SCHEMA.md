# Motion event schema (`RUN/motion_events.json`, `egohand_motion_events/0.1`)

**Producers:** `egohand events RUN`, and every backend run (written after the side vote). **Consumers:** the viewer's events strip and list (hold, movement and long gap; entry and exit duplicate the lanes) and the review buttons.

```json
{"event_id": "mev00012", "track_id": 4, "hand": "right|left|unknown", "event_type": "candidate_hold",
 "start_time_s": 12.4, "end_time_s": 14.1, "evidence_frames": [372, 390, 423], "status": "inferred",
 "quality_flags": ["side_unknown", "fitted_3d"], "review_status": "unreviewed|confirmed|rejected",
 "basis": "wrist image speed < 0.08/s for >= 1.0 s"}
```

**Types:**
- `hand_entry`, `hand_exit` (with the tracker's inferred reason);
- `long_gap` (more than 1 s unobserved, then reacquired);
- `candidate_hold` (5-frame median wrist image speed < 0.08 diagonals/s for ≥ 1 s);
- `candidate_movement` (> 0.3/s for ≥ 0.3 s).

**Limits:**
- **Untested thresholds.** They are heuristics with no labelled events behind them.
- **No camera-motion compensation,** so head motion counts as hand motion. This is why holds are rare: 1 in the 90 s holdout run.
- **No claims of contact or action.** A hold is not a grasp.

**Review:** Confirm and Reject in the inspection panel store a decision (`POST /api/runs/<id>/review-queue/<event_id>/decisions`; confirm = `confirmed_issue`, reject = `false_alarm`). `GET /api/runs/<id>/decisions` restores it on reload. Verified end to end in Chromium.
