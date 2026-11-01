# MOTIONIQ backend API (v1)

A Django service that wraps the `motioniq` pipeline for the frontend. It runs locally and is private: it reads restricted factory footage, so it binds to 127.0.0.1, serves only files under allowed folders, and can require a token.

## Run it

```sh
uv sync --extra dev --extra viewer --extra backend
uv run motioniq fetch-model
cd backend
uv run python manage.py migrate
uv run python manage.py motioniq_register ../media             # every video in a folder (or list files)
uv run python manage.py runserver 127.0.0.1:8000           # API
uv run python manage.py motioniq_worker --recover           # job worker (second terminal)
```

Then open **http://127.0.0.1:8000/** for the viewer (`frontend/prototype/index.html`, served by Django with `backend-connector.js`). Choose a completed run and click **Load run**, or queue a new one with **Process**.

Proxy encoding needs FFmpeg support for `-fps_mode passthrough` and `-enc_time_base filter`. The frame-selection and timestamp regressions were verified with FFmpeg 9.0.2.

Environment variables (all optional):

| Variable | Default | Meaning |
| --- | --- | --- |
| `MOTIONIQ_MEDIA_ROOTS` | `<repo>/data/private` and `<repo>/media` | Folders from which videos may be registered and served, separated by `;` on Windows or `:` on Unix |
| `MOTIONIQ_UPLOAD_DIR` | `<repo>/data/private/uploads` | Dedicated trusted upload folder; uploads work even when media roots point elsewhere |
| `MOTIONIQ_CORS_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173` | Frontend dev origins allowed by CORS |
| `MOTIONIQ_API_TOKEN` | empty (no auth) | If set, send `Authorization: Bearer <token>`. For `<video src>` and `<img src>`, append `?token=<token>`. `/api/health` stays open. |
| `MOTIONIQ_RUNS_DIR` | `<repo>/runs/backend` | Where run outputs are written |
| `MOTIONIQ_DATA_DIR` | `<repo>/data/private/backend` | Database, frame-image cache, timestamp cache |
| `MOTIONIQ_GOVERNANCE_FILE` | empty | `governance.json` passed to every run (consent, retention, lens source) |
| `MOTIONIQ_MAX_FRAMES_PER_REQUEST` | 600 | Upper limit for `/frames` pages |
| `MOTIONIQ_LIFT_HFOV` | 150 | Horizontal FOV for the EXPERIMENTAL assumed-lens lift the worker writes for the viewer's camera-space panel; empty disables it |
| `MOTIONIQ_FRONTEND_DIR` | `<repo>/frontend/prototype` | Folder of the viewer page served at `/` |

## Conventions

- **JSON:** everything is JSON except media. JSON request bodies require `Content-Type: application/json` (a charset is allowed); uploads use multipart. Errors are `{"error": "..."}` with status 400 (bad input), 401 (token), 403 (path or request origin not allowed), 404 (not found), 405 (method), 409 (not ready or unsafe run output path), 415 (wrong JSON content type), or 503 (run output deletion failed; retry).
- **Browser writes:** POST, PUT, PATCH and DELETE under `/api/` accept the service's own origin or an origin in `MOTIONIQ_CORS_ORIGINS`. Cross-site browser requests without an `Origin` are rejected. CLI requests without browser origin headers remain supported.
- **Time:** times are seconds on the **run time base**: seconds since the first presentation timestamp of the source video, the same as `timestamp_s` in frames. The proxy starts at the first selected source frame, so `run_time = run.proxy.time_offset_s + video.currentTime`. For fractional requested starts this offset can differ from `run.start_s`; use the persisted proxy metadata.
- **Source integrity:** a registered path keeps its original content identity. If its size or modification time changes, the service rechecks the SHA-256 before reading or processing it. Changed content returns 409; restore the original file or register the new content at a new path. Cached integrity checks assume local files are not changed while preserving both size and modification time. Existing completed proxies remain available independently of the original source.
- **Image coordinates:** `image_xyz` x and y are normalized to the frame (0–1). To draw on a `<video>` element, multiply by the displayed video width and height (keep the aspect ratio; the proxy is 960 px wide, 16:9 for the official clips). z is model depth, not metric.
- **3D:** `world_xyz_m` is MediaPipe's hand-relative estimate in metres (origin near the hand centre). It is **not** camera or factory coordinates; spacing between hands in a 3D view is arbitrary.
- **States:**
  - `observed` / `reacquired`: drawn solid.
  - `predicted`: 2D only and extrapolated; draw dashed or grey, and never as a detection.
  - `lost` / `retired`: no coordinates.
  - `missing_reason` is an inferred hint (`out_of_view` or `unknown`).
- **Side probability:** `side_probability_right_smoothed` (show as `p_R`) is left/right confidence only, not landmark quality.

## Endpoints

### Service

| Method and path | Response |
| --- | --- |
| `GET /api/health` | `{status, api_version, model_present, auth_required, queue: {queued, running}}` |
| `GET /api/presets` | `{presets: {baseline, recall, accurate}, default}`, with measured notes (provisional labels) |

### Videos

| Method and path | Body / query | Response |
| --- | --- | --- |
| `GET /api/videos` | — | `{videos: [Video]}` |
| `POST /api/videos` | `{"path": "/abs/path/under/media/root.mp4"}` | `201 Video` (re-registering returns the same video) |
| `POST /api/videos/upload` | multipart field `file` (.mp4, .mov, .mkv, .avi) | `201 Video`; stored under `data/private/uploads` |
| `GET /api/videos/<id>` | — | `Video` plus `runs: [Run]` |
| `GET /api/videos/<id>/frames/<frame_index>.jpg` | `?width=640` | The exact source frame as JPEG. About 1.5 s cold, then cached (about 6 ms). Prefer the proxy video for playback. |

`Video = {id, name, sha256, width, height, fps, frame_count, duration_s, timestamp_source, created_at}`

### Runs (processing jobs)

| Method and path | Body / query | Response |
| --- | --- | --- |
| `POST /api/runs` | `{"video_id": 1, "preset": "recall", "start_s": 0, "duration_s": 30, "workers": 2, "render_preview": false, "write_rrd": false}` | `202 Run` (queued) |
| `GET /api/runs` | `?video_id=&status=` | `{runs: [Run]}` (newest first) |
| `GET /api/runs/<id>` | — | `Run` plus `metrics`, `quality_summary`, `video`, `proxy` and `artifacts`. **Poll this about once per second while running.** |
| `POST /api/runs/<id>/cancel` | — | `Run` (`cancelled`); 409 if already finished |
| `DELETE /api/runs/<id>` | — | 204 after deleting the outputs this backend created; 409 while queued or running; 503 if output removal fails (record remains for retry) |

`Run = {id, video_id, preset, start_s, duration_s, workers, render_preview, write_rrd, status, stage, progress, error, created_at, started_at, finished_at}`
- `status`: `queued | running | complete | failed | cancelled`.
- `stage`: `queued → processing → quality → indexing → proxy → complete`.
- `progress`: 0–1.
- `proxy`: `{path, width, frames, time_offset_s, frame_index_range, timestamp_mode}` from `proxy.json`, or null when unavailable. Newly verified proxies carry `timestamp_mode: "source_pts"`; older proxies without that marker are not advertised or served as frame-exact. Submit a new run to regenerate one without overwriting prior outputs.
- `artifacts`: `{identity: "identity.json" | null, lift: {summary, arrays} | null}`. Lift names come from an existing matching pair, including non-default FOVs; no lift is advertised when disabled or absent. If several supported pairs exist, the first filename in sorted order is selected.

Intervals must contain an actual source presentation timestamp. A start beyond the final frame or an empty fractional interval returns JSON 400 before queuing.

Everything below needs `status == complete` (409 before that).

### Frames (overlay data)

| Method and path | Query | Response |
| --- | --- | --- |
| `GET /api/runs/<id>/frames` | `start_s`, `end_s` (half-open), `detail=lite\|full`, `max_frames` (≤600) | `{frames, count, truncated, next_start_s, detail}`. If `truncated`, request again from `next_start_s`. |
| `GET /api/runs/<id>/frames/<frame_index>` | `detail=full\|lite` | One frame record |

- **Lite frame:** `{frame_index, timestamp_s, quality: {blur_laplacian_var, mean_luma, masks}, hands: [{track_id, state, observed, side, side_probability_right_smoothed, anatomical_side, detection_origin, missing_reason, seconds_since_observed, image_xyz (21×3 | null), world_xyz_m (21×3 | null)}]}`. Values are rounded to 4 decimals.
- **Full frame:** the unchanged `landmarks.jsonl` record, including raw values, provenance and `missing_reason_basis`. It validates against `src/motioniq/schemas/motioniq_frame.schema.json`.
- **Landmark order:** MediaPipe 21-point order (0 wrist; 4, 8, 12, 16, 20 fingertips). Bones are listed in `motioniq.model.CONNECTIONS`.
- **Suggested client pattern:** fetch 2–5 s windows ahead of the playhead and look up the nearest `timestamp_s` for each `requestVideoFrameCallback`.

### Timeline, quality and review

| Method and path | Response |
| --- | --- |
| `GET /api/runs/<id>/tracks` | `{tracks: [{track_id, observed_frames, segments: [{state, side, start_s, end_s, frames, missing_reason}]}]}` for state lanes (`end_s` inclusive) |
| `GET /api/runs/<id>/events` | `?start_s&end_s` → `{events: [{frame_index, timestamp_s, track_id, side, from_state, to_state, missing_reason}]}` |
| `GET /api/runs/<id>/quality` | `{summary, windows}` (`?windows=0` for the summary only). Windows are 1 s: `{start_s, end_s, first_frame, last_frame, status: suitable\|needs_review\|insufficient_evidence, reasons, track_ids, evidence}` |
| `GET /api/runs/<id>/review-queue` | `?status=needs_review` → `{items, count}`, ranked by priority. Item: `{item_id, status, start_s, end_s, first_frame, last_frame, track_ids, reason_window_counts, priority_score, suggested_actions, assessment_source, windows, decisions}` |
| `POST /api/runs/<id>/review-queue/<item_id>/decisions` | `{"verdict": "confirmed_issue\|false_alarm\|exclude\|needs_more_review", "reviewer": "UB", "note": ""}` → `201` |
| `GET /api/runs/<id>/review-stats` | `{flagged_items, reviewed_items, confirmed_issue, false_alarm, flag_precision, by_reason}`, using the latest decision per item |

Quality statuses are **heuristic, task-specific** assessments. `insufficient_evidence` means no *observed* hand, not "no hand". Show the `reasons` and `evidence` next to every flag.

### Media and files

| Method and path | Response |
| --- | --- |
| `GET /api/runs/<id>/proxy.mp4` | Clean H.264 of the selected source frames (960 px), with their relative presentation times preserved; supports Range. Legacy unverified proxies return 409. Use it as `<video src>` and apply `proxy.time_offset_s` to overlays from `/frames`. |
| `GET /api/runs/<id>/preview.mp4` | Side-by-side rendered preview (only if the run was submitted with `render_preview: true`) |
| `GET /api/runs/<id>/compare.jpg?t=6.0` | Same-moment flat frame vs three 3D views of each observed hand. 404 with the nearest observed frames if that moment has no observed hand. About 1.6 s cold, then cached. |
| `GET /api/runs/<id>/manifest` | `manifest.json`: hashes, parameters including the preset, governance, lens provenance |
| `GET /api/runs/<id>/artifacts/<name>` | Download one of: `landmarks.jsonl`, `landmarks.csv`, `landmarks.npz`, `manifest.json`, `metrics.json`, `tracking_events.csv`, `replay.rrd`, `quality/review_queue.csv`, `quality/quality_frames.csv`, `identity.json`, `lift_hfov<NNN>.json`, `lift_hfov<NNN>.npz` |

## Measured latency (4-vCPU Linux VM, 31 Oct 2026)

| Operation | Time |
| --- | --- |
| `GET /runs/<id>`, `/tracks`, `/quality`, `/review-queue`, `/events`, `/frames/<n>` | 5–6 ms |
| `GET /frames`, 2 s window, lite | 27–32 ms (18 KB gzip; 92 KB uncompressed) |
| `GET /frames`, 2 s window, full | about 40 ms (102 KB gzip) |
| Frame JPEG, cold → cached | 1.48 s → 6 ms |
| Process 30 s of 1080p, recall preset, no preview | 63.2 s with 1 worker → 50.4 s with 2 workers (identical detections). The quality pass, indexing and proxy add about 25 s. |
| Process 30 s of 1080p, accurate preset (recall + reverse-time pass), 2 workers | 101 s for detection and exports; the quality pass, indexing and proxy add about 25 s. |

## Not provided

- Meshes, robot export, world/factory coordinates.
- Privacy detection.
- User accounts. Use the shared token on a trusted machine only. **Do not expose this service on a public interface.**

`GET /api/videos/<id>/frame-at?time_s=<seconds>` resolves a still-preview start to the first source frame at or after that time. It returns `frame_index` and the source-relative `timestamp_s`; invalid or out-of-range times return 400. This uses presentation timestamps for variable-frame-rate sources.
