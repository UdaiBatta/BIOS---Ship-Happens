# To-do (deferred work, 31 Oct 2026)

None of these exists in the code or the results. Do not present any of them as done.

| # | Item | Blocker / gate | First step |
| --- | --- | --- | --- |
| 1 | WiLoR/MANO meshes | Needs a GPU host, authorized MANO assets and a licence check (WiLoR CC-BY-NC-ND, MANO non-commercial) | Benchmark 20 fixed frames in an isolated environment, outside the public repo ([WILOR_FEASIBILITY.md](WILOR_FEASIBILITY.md)) |
| 2 | Robot-ready export (wrist pose, palm normal, grip aperture, Aria-compatible CSV, LeRobot episodes) | Needs calibrated camera-space geometry, a named downstream task, a robot representation and transforms | Get the lens intrinsics from the organizers, or calibrate an own recording |
| 3 | Bone-length calibration | Needs a reliable anatomical identity per track | Report raw vs adjusted bone CV plus side effects; never fit on holdout frames |
| 4 | Candidate privacy flags (faces, screens, text) | Needs a labeled evaluation set for misses and false alarms | Label about 50 frames for faces/screens; review assistance only, never certification |
| 5 | Bounded action/context events (enter/leave, motion onset/pause) | Needs reviewed interval labels | Derive from `tracking_events.csv` and wrist speed; no semantic actions without object evidence |
| 6 | "Does 3D beat video?" user test | Needs 3–5 participants | Protocol in [DEMO_AND_QA.md](DEMO_AND_QA.md) |
| 7 | Review-time pilot (plain video vs queue) | Needs participants and reviewed ground-truth intervals | Protocol in [DEMO_AND_QA.md](DEMO_AND_QA.md) |
| 8 | Dual-label a subset; report agreement; then `reviewed=true` and re-score | Needs a second person | Start with uncertain-side and truncated hands in `data/private/labels_v2/` |
| 9 | Other recording families (SGF00106, SKL00089, 000003) | Drive downloads blocked in this environment | Download one clip per family locally; rerun the evaluation |
| 10 | Lens calibration / organizer intrinsics | Organizer answer | Draft questions in [PRODUCT_BRIEF.md](PRODUCT_BRIEF.md) |
