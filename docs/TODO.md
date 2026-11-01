# To-do (1 Nov 2026)

These items remain open. The viewer, smoothing, generated hand surface with bone-length calibration, heuristic motion-event candidates and experimental face-only flags are already implemented; they need evaluation where noted below.

| # | Item | Blocker / gate | First step |
| --- | --- | --- | --- |
| 1 | Fitted WiLoR/MANO meshes | Requires authorized model assets and a licence check (WiLoR CC-BY-NC-ND, MANO non-commercial); no fitted model is integrated | Benchmark fixed frames in an isolated environment, outside the public repo ([WILOR_FEASIBILITY.md](WILOR_FEASIBILITY.md)) |
| 2 | Robot-ready export (wrist pose, palm normal, grip aperture, Aria-compatible CSV, LeRobot episodes) | Needs calibrated camera-space geometry, a named downstream task, a robot representation and transforms | Get the lens intrinsics from the organizers, or calibrate an own recording |
| 3 | Rescore common accuracy | Current-session `labels_v2` inputs are missing | Restore authorized labels, review them independently, then rerun the evaluation |
| 4 | Evaluate across recording families | Needs labeled examples from each family | Label a representative subset and report per-family results |
| 5 | Validate privacy flags and motion events | Face flags are experimental; event thresholds are heuristic and lack labeled evaluation | Label candidate and missed intervals, then report false alarms and misses |
| 6 | "Does 3D beat video?" user test | Needs participants | Protocol in [DEMO_AND_QA.md](DEMO_AND_QA.md) |
| 7 | Review-time pilot (plain video vs queue) | Needs participants and reviewed ground-truth intervals | Protocol in [DEMO_AND_QA.md](DEMO_AND_QA.md) |
| 8 | Lens calibration / organizer intrinsics | Calibration input is not verified | Confirm lens parameters or calibrate an authorized recording |

## After the code review (viewer and backend caveats, 31 Oct 2026)

| # | Item | Why | First step |
| --- | --- | --- | --- |
| 11 | Validate camera-space depth | The viewer's 3D panel uses an **assumed** equidistant fisheye lens (HFOV 150°); depth is not validated, and the label says so | Get the organizer intrinsics, or calibrate a consented own recording; measure depth error in cm before removing the "experimental" label |
| 12 | Replace historical provisional evidence with current reviewed accuracy | Current-session common accuracy is unmeasured; local rescore labels are missing | Restore labels, conduct independent review, then re-score across recording families |
| 13 | Recover hands cut off at the bottom edge | Still often missed (7/23 on holdout; visible in the 60–70 s run); cheap crop variants did not help | RTMDet-nano (hand) tried as `--preset hybrid`: no gain on dev and more false positives. Next: a detector trained on egocentric hands, or WiLoR/HaMeR (licence and GPU) |
| 14 | Keep restricted footage local in demos | The viewer plays a proxy of restricted footage | Keep the server on 127.0.0.1; no screenshots in public material; consider refusing non-local binds without a token |
| 15 | Smoother token handling | With `MOTIONIQ_API_TOKEN` set, the page must be opened once as `/?token=…`, and the token travels in media URLs | Replace with a short login that sets an HttpOnly session cookie |
| 16 | Faster first Process click on large videos | The first `POST /api/runs` per server process hashes the whole source video in the request (seconds for multi-GB files); the worker checks again | Store size and mtime on `Video` and hash only when they change |
| 17 | Faster proxy for runs late in long videos | The frame-exact proxy decodes the video from frame 0 up to the run start | Seek the input to just before the first frame and select by timestamp; keep the frame-count check |
| 18 | Benchmark on the team laptop | All timings come from a 4-vCPU cloud VM | `uv run python scripts/benchmark_hybrid.py data/private/<clip>.mp4 --duration 30` |
| 19 | Label two-hand frames from the team's recording families | Same-side pairs and hybrid precision cannot be measured on unlabelled families | About 50 frames per family with `motioniq annotation-set`; then `scripts/compare_baseline.py` |
| 20 | Monocular depth test (Depth Anything V2 Small) | Possible hand-vs-background filter for hybrid candidates; untested | Upload the model like the RTM models; follow [DEPTH_FEASIBILITY](DEPTH_FEASIBILITY.md) §4 |
| 21 | Camera-motion-aided prediction | Head motion moves still hands across the image; not compensated | Background optical flow (excluding hand boxes) to shift track predictions; measure ID changes |
| 22 | Try `hybrid` + reverse-time pass together | Not tested for time reasons | Dev first; the go/no-go rule in [EXPERIMENT_RESULTS](EXPERIMENT_RESULTS.md) |
