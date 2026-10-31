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

## After the code review (viewer and backend caveats, 31 Oct 2026)

| # | Item | Why | First step |
| --- | --- | --- | --- |
| 11 | Validate camera-space depth | The viewer's 3D panel uses an **assumed** equidistant fisheye lens (HFOV 150°); depth is not validated, and the label says so | Get the organizer intrinsics, or calibrate a consented own recording; measure depth error in cm before removing the "experimental" label |
| 12 | Replace coverage-only evidence with reviewed accuracy | The viewer's coverage chip is coverage, not accuracy; all accuracy figures come from unreviewed labels on one clip | Human label review (`egohand label-review`), clips from other recording families, re-score |
| 13 | Recover hands cut off at the bottom edge | Still often missed (7/23 on holdout; visible in the 60–70 s run); cheap crop variants did not help | Benchmark a dedicated hand detector in an isolated environment (licence check first) |
| 14 | Keep restricted footage local in demos | The viewer plays a proxy of restricted footage | Keep the server on 127.0.0.1; no screenshots in public material; consider refusing non-local binds without a token |
| 15 | Smoother token handling | With `EGOHAND_API_TOKEN` set, the page must be opened once as `/?token=…`, and the token travels in media URLs | Replace with a short login that sets an HttpOnly session cookie |
