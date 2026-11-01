# MOTIONIQ pre-merge review

What this change does: restores hand meshes in posture and camera fallback views, reduces finger twitching while preserving raw observations, and renames the product and its commands to MOTIONIQ. The review assumes one user processing private clips on a local laptop.

## Findings fixed before merge

1. Variable-frame-rate still previews used average FPS to choose a source frame. The backend now resolves start time against cached presentation timestamps; the frontend uses the returned frame and ignores stale responses. A backend regression test and a synthetic browser check cover this.
2. The common deliverable renderer could silently replace variable source timing with constant FPS. It now rejects variable or unverified frame-rate manifests before rendering. Tests cover both cases; timestamp-aware VFR deliverable rendering remains unsupported.
3. Concurrent remote changes introduced a second FFmpeg finder and competing camera controls. The merge shares one tool finder, honors explicit configuration first, preserves posture meshes and fallback, and retains camera depth cues, near-plane clipping and track-specific wrist trails.

## Rename and compatibility

The UI, Python package, CLI, Django package and commands, schemas, documentation, exports and editable slide artifacts use MOTIONIQ. Legacy environment and browser-storage aliases preserve existing private installations. Private artifacts, the database, Git history and the remote repository name are unchanged.

## Verification

- Core: 202 passed, 1 skipped. Backend: 43 passed.
- JavaScript and PowerShell syntax checks pass; staged diff checked for conflict markers and whitespace errors.
- Chromium: synthetic meshes, skeleton/both, raw/smoothed, camera fallback, orientation presets, follow/reset, 390/1024 px layouts and timestamp-preview resolution pass without page exceptions. The Browser plugin was unavailable, so checks used installed Playwright.
- Existing prepared run: 900 frames load; all 1,324 observed hand samples retain world joints, posture wrists stay anchored and generated meshes remain bounded to 64 cached entries.
- Renamed PPTX and PDF each contain six slides; branding and metadata checked and the cover inspected visually.
- Preflight passes tools, local API, worker, saved run, readable frames and disk checks. Power currently reports battery, so the complete presentation preflight is not passing.

An older broad UI harness timed out on obsolete status/fixture assumptions. Targeted current-flow checks replaced it; this does not complete the broader P1 rehearsal plan in BUG_BASH.md. Cold starts, human backup recording, all-clip benchmarking and reviewed confidence calibration remain pending.

Verdict: Ship the reviewed software changes. Connect AC power before presenting or benchmarking.
