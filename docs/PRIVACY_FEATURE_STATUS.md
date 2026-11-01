# Privacy flags: status (experimental, not in the viewer)

**Command:** `egohand privacy VIDEO RUN --every 1` → `RUN/privacy_flags.json`.
- **Model:** MediaPipe Face Detector, BlazeFace short range (Apache-2.0, SHA-256 pinned, fetched into the git-ignored `models/`).
- **Sampling:** one frame per second.
- **Each flag records:** time, frame, normalised box, score, category `face_candidate`, source and review status.

**Measured on the 90 s holdout interval:**
- 90 frames checked, **2 candidates, both false alarms** (a bright doorway and a bright window);
- small distant people in the second frame were **not** flagged.

So it is **not useful at this setting** on this footage, and it is not integrated into the viewer.

**Not checked at all:** screens, documents, badges and other identifying details. Results describe processes, never individual workers.

**Next steps:**
- label about 50 frames with people;
- try the full-range face model or a person detector;
- measure misses and false alarms before relying on it.
