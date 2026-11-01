# Submission bug bash

Verified on the local Windows laptop on 1 Nov 2026, branch `udai-s1`. Footage, run outputs and review images remain in ignored local folders. Saved UI screenshots use synthetic data only.

| Check | Result | Evidence |
| --- | --- | --- |
| Pipeline suite | PASS | `uv run pytest -q`: 202 passed, 1 skipped. |
| Backend suite | PASS | From `backend`, `uv run python manage.py test`: 42 of 42 passed; no system-check issues. Expected error-path logs are part of the tests. |
| All offered presets | PASS | Baseline, recall, accurate and hybrid each completed a five-second registered-video run with no app console/page errors or failed requests in the successful flow. |
| Longer accurate run | PASS after fix | Unused full-resolution frame retention was removed from crop-rescue reverse processing. Corrected thirty-second processing completes and loads its selected frames. The earlier native failure remains a failed warm-up, not a speed result. |
| Empty 3D panel | FIXED | Hand posture is the default; loading a run preserves the mode. Camera rejection no longer discards hand-relative posture. Labels distinguish posture from camera placement. |
| Mesh availability | FIXED | Mesh and Mesh + skeleton render from observed hand-relative joints without requiring camera depth. Synthetic checks cover finite vertices, raw/smoothed modes, camera fallback and exclusion of predicted poses. |
| Affected clip | PASS for checked cases | Prepared run: 900 frames, 1,324 observed hand samples; all have hand-relative joints and 761 lack camera joints. Meshes render at all six inspected problem/control frames. Illustrative wrist drift is zero across the run. No real-footage screenshots were made. |
| Temporal stability | MEASURED | Both fresh runs have identical raw observations. Angular twitch falls 37.56% at the 90th percentile across 1,251 hand triples / 20,016 bone samples. Extreme deviation from raw increases. See POSE_STABILITY; this is not accuracy. |
| Workspaces / splits | PASS | Review, Analysis, Diagnostics and every split preset update real UI state. |
| View controls | PASS | Side, Top, Camera, follow, wheel zoom and reset exercised. Reset restores distance, orientation and follow state. |
| Responsive layout | PASS | Analysis and Diagnostics fit 390 px and 1,024 px widths without overflow. Responsive grid areas were corrected. |
| Timeline / events | PARTIAL | Event-list seek, zoom, F and R pass. Drag-selection proof is incomplete. |
| Synthetic upload / unprocessed video | PASS | Small synthetic upload registers and shows an unprocessed preview without synthetic tracking. |
| Cached rendering tool | PASS smoke check | Synthetic input renders a verified H.264/yuv420p MP4 with the expected frame count. |
| Prepared-run preflight | PASS | Tools, local API, project worker, completed run, readable frames, disk and AC checks pass. Cold starts and a human backup recording remain pending. |

The 3D finger filter separates lengths and directions and uses adjacent observed samples with timestamp-aware interpolation. Raw fields are preserved, and filtering does not cross track/gap boundaries. Hand posture is wrist-centered with illustrative placement; camera-space acceptance masks are unchanged.

Procedural meshes use per-track bone profiles and an on-demand cache capped at 64 entries. Imported camera-space meshes retain their coordinate frame. This is not fitted MANO/WiLoR inference. Side score means left/right classifier support; landmark confidence remains uncalibrated.

ONNX Runtime was repaired before final verification. Native tests ran with normal Windows permissions, workspace-local temporary/cache folders, and the configured FFmpeg directory. Pixel-count instrumentation produced a Canvas2D readback-performance warning. Local seeking produced media requests ending in `net::ERR_ABORTED`; these are cancellations. No app page exceptions occurred in the final mesh checks.

Still pending in the original full P1 plan: rendered Confirm/Reject persistence, stopped-worker queue messaging, temporarily missing synthetic-file recovery, drag-selection proof, full-interval visual review, cold-start rehearsals and a human-recorded backup. API error-path coverage does not replace these browser checks. P1 is not claimed complete as a whole. Fix revisions are recorded in branch history.
