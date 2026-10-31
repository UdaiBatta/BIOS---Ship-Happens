# Smoothing comparison (why raw looked better)

**Root cause:** the old One Euro filter used `beta = 0.03` in normalised image units. Hand speeds are about 0.5 units/s, so it acted as a fixed 1.7 Hz low-pass and trailed fast hands by 65–80 px. It was applied to all 21 joints independently and was keyed per track (no cross-track contamination; reset after 0.2 s gaps).

**Compared on identical tracks**, against labelled wrists (provisional labels; 1920×1080 px):

| Configuration | Dev wrist error median / mean | Dev wrist jitter | Fingertip jitter (rel. wrist) | Fast-motion offset from raw |
| --- | --- | --- | --- | --- |
| A raw | 28.7 / 32.6 | 19.9 | 24.2 | 0 |
| B old One Euro | 48.1 / 65.4 | 10.1 | 6.8 | 81.5 |
| C One Euro, pixel units (1.0, 0.05) | 30.0 / 33.7 | 18.0 | 19.0 | 11.0 |
| D wrist Kalman (forward) + One Euro fingers | 32.4 / 34.5 | 17.1 | 15.4 | 8.9 |
| F offline RTS wrist + raw fingers | 31.5 / 33.0 | 12.5 | 24.2 | 8.2 |
| **Chosen:** RTS wrist (q = 4000) + One Euro fingers relative to the wrist | 30.1 / 32.9 | 13.7 | 15.4 | 5.1 |

**Holdout, once:** chosen 26.6 / 32.6 px against raw 25.3 / 32.7 and old 45.3 / 53.2; wrist jitter 16.2 → 8.1; fingertip jitter 21.9 → 12.7; lag 65 → 6 px.

**Not adopted:**
- **E, bone-length-constrained 2D smoothing.** 2D bone lengths change with foreshortening. Bone-length calibration is applied to the mesh instead ([HAND_MESH_ARCHITECTURE](HAND_MESH_ARCHITECTURE.md)).
- **Savitzky–Golay and quaternion joint-angle smoothing.** Not tried for time reasons.

**Implementation:** `src/egohand_twin/smoothing.py`, an offline pass before the exports are written. Raw values are never modified, and the viewer's Raw/Smoothed toggle still compares them.
