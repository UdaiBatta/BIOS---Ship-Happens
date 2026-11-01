# Submission readiness

Work is in progress on `udai-s1`. The project is not yet ready for final submission or publication.

Latest priority: stabilize 3D posture and restore mandatory mesh rendering. Those changes are implemented and browser-checked; the broader submission measurements remain pending.

## Agreed scope

- Audit the existing private repository for eventual publication (option B). No visibility change, release deletion or history rewrite is authorized by this audit.
- Evaluate the first 30 seconds of all 36 common clips for the first comparison. This interval supersedes the original full-clip instruction for this pass.
- Keep footage, frames, labels, run outputs and processed videos in ignored local folders. Public slides contain no footage.

| Phase | Current evidence | Remaining work |
| --- | --- | --- |
| P0 | Option B selected | Resolve publication findings before any visibility decision |
| P1 | 197 pipeline tests passed, 1 skipped; 42 of 42 backend tests passed. Posture meshes, wrist consistency and the prepared run pass browser checks | Remaining rendered error-path and event-persistence checks; see BUG_BASH |
| P2 | Documentation, verified test counts and demo script corrected | Add the eventual isolated laptop benchmark |
| P3 | Reproducible evaluator and coverage-report generator implemented | Run the full agreed comparison and retain private outputs |
| P4 | 1,080 unlabeled frames prepared across 36 clips, with independent shared-frame copies | People label them; validate, score and measure agreement |
| P5 | Historical private handoff restored and checksummed | Original `labels_v2` files are missing; an independent person must review them before rescoring |
| P6 | Laptop is connected to AC; warm-up exposed an accurate-preset native failure; its reduced-buffer run now completes in the viewer | Finish the isolated preset benchmark and update performance/slides |
| P7 | Cached-render tool implemented and verified with a synthetic MP4 | Render the common clips, verify and list MP4s; a person uploads only to the designated private Drive folder |
| P8 | Pilot protocol exists | Participants and measured results are still needed |
| P9 | Editable six-slide draft and matching PDF prepared without footage | Add final measured evidence; teammate readthrough |
| P10 | Fresh remote-history scan passes; publication audit identifies release attachments and historical internal text | See PUBLICATION_AUDIT; publication is not cleared |
| P11 | Prepared thirty-second accurate demo and its local preflight pass; direct run URL supported | Rehearse cold starts and record/play the human backup |
| P12 | No merge performed | Final gates, PR, human approval, merge commit and laptop verification |
| P13 | Current claims and rehearsal topics are in DEMO_SCRIPT | Presenters answer and rehearse the questions |

## Local handoff

The current annotation set is `data/private/labels_common_first30/README.txt`. It is separate from the earlier interrupted full-clip set. Every pack is unreviewed. Old accuracy figures in experiment reports remain explicitly historical and provisional.

See [bug bash](BUG_BASH.md), [common results](COMMON_CLIPS_RESULTS.md), [performance](PERFORMANCE_REPORT.md), [demo script](DEMO_SCRIPT.md) and [publication audit](PUBLICATION_AUDIT.md) for evidence and limitations. A phase is complete only when its remaining work is actually finished.
