> **Superseded (31 Oct 2026).** These were the original hour-by-hour gates. Current status, priorities and deferred work are in [PRODUCT_BRIEF.md](PRODUCT_BRIEF.md) and [TODO.md](TODO.md).

# Hackathon execution gates

This repository starts with the first functioning milestone. It does not imply that all PS4 bonuses or a complete submission are finished.

1. **Working minimum (by hour 6):** process actual factory footage; inspect both hand skeletons and raw/filtered exports; verify known left/right, no phantom 3D during loss, and decoded video timing. Cache a 30–60 second demonstration. Keep a plain baseline for comparison.
2. **Accuracy evidence (hours 6–10):** choose representative intervals across all four recording families. Label 50–100 frames with visible hands and persistent anatomical identity; label joints on a smaller subset. Compare raw detector, tracking and smoothing independently. Report sample selection, thresholds, failures, precision/recall, sampled ID changes and p50/p95 latency. Freeze a holdout before threshold tuning.
3. **Mesh gate (hours 10–12):** obtain an authorized MANO model and a verified GPU host if available. In an isolated environment, benchmark WiLoR on 20–50 fixed frames. Measure wall time, peak VRAM, valid meshes and visible failure cases. Integrate only if the benchmark works; preserve the MediaPipe fallback.
4. **Optional camera tracking (stop by hour 15):** only attempt after the above deliverables. A camera trajectory alone does not provide hand-root depth or metric scale. Require validated intrinsics, coordinate conventions, scale and hand-root translation before calling results world-space.
5. **Evaluation and rehearsal (hours 17–20):** process common official clips, cache final recordings, test exports with a second reader, and record a five-minute demo. An industrial usefulness experiment can measure event-finding time with ordinary video versus the structured replay; report actual results only.
6. **Submission freeze (hours 20–24):** public source-only GitHub repository; processed clips in the designated private folder; 5–6 slides; offline demo fallback and 3-minute Q&A rehearsal. No private footage in repository history or attached public screenshots.

Suggested five-minute demo: 0:00 problem and source footage; 0:35 observed hands and 3D skeleton; 1:30 pause, rotate and inspect; 2:15 loss/reacquisition and limitations; 3:00 measured baseline comparison; 4:00 exports and industrial use; 4:40 honest scope and next steps.

Unvalidated claims to avoid: absolute factory coordinates, accurate inter-hand distances, robust identity through arbitrary occlusions, real-time throughput on untested hardware, mesh quality improvements, or factory productivity gains.
