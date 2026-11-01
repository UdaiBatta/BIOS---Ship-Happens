"""End-to-end API tests on synthetic data (no MediaPipe inference: the pipeline is faked)."""
from __future__ import annotations

import csv
import json
from pathlib import Path
import tempfile

import cv2
import numpy as np
from django.test import TestCase, override_settings

from api import jobs
from api.models import Run

FPS = 10
N = 40


def make_video(folder: Path) -> Path:
    path = folder/"clip.avi"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), FPS, (160, 90))
    for i in range(N):
        writer.write(np.full((90, 160, 3), 6*i, np.uint8))  # frame i has gray level 6*i
    writer.release()
    return path


def fake_process(args, progress=None, workers=1):
    """Writes a schema-shaped run like motioniq.pipeline.process would."""
    from motioniq.model import sha256
    out = Path(args.out)
    out.mkdir(parents=True)
    lines, events = [], []
    start = args.start_seconds
    end = start + args.duration if args.duration else N/FPS
    for i in range(N):
        t = i/FPS
        if not start - 1e-9 <= t < end - 1e-9:
            continue
        hands = []
        flicker = 10 <= i < 20 and i % 2  # 1-2 s: detected only every other frame
        if (i < 20 or i >= 30) and not flicker:  # observed, missing for 1 s, then a new track
            tid = 1 if i < 20 else 2
            image = np.zeros((21, 3))
            image[:, 0] = .4 + np.linspace(0, .05, 21)
            image[:, 1] = .6 - np.linspace(0, .1, 21)
            world = (image - image.mean(0))*.3
            hands.append({"track_id": tid, "state": "observed", "observed": True, "side": "Left",
                          "side_probability_right_smoothed": .1, "anatomical_side": "unknown",
                          "detection_origin": "full_frame", "missing_reason": None,
                          "seconds_since_observed": 0., "handedness_score": .9, "raw_side": "Left",
                          "image_xyz": image.tolist(), "image_xyz_raw": image.tolist(),
                          "world_xyz_m": world.tolist(), "world_xyz_m_raw": world.tolist()})
        elif i < 28 or flicker:
            hands.append({"track_id": 1, "state": "lost", "observed": False, "side": "Left",
                          "side_probability_right_smoothed": .1, "anatomical_side": "unknown",
                          "missing_reason": "unknown", "seconds_since_observed": t-1.9,
                          "image_xyz": None, "image_xyz_raw": None, "world_xyz_m": None, "world_xyz_m_raw": None})
        lines.append(json.dumps({"frame_index": i, "timestamp_s": t, "source_pts_s": t, "hands": hands}))
        if progress:
            progress(i+1, N)
    (out/"landmarks.jsonl").write_text("\n".join(lines)+"\n")
    with (out/"tracking_events.csv").open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["frame_index", "timestamp_s", "track_id", "side", "from_state", "to_state", "missing_reason"])
        writer.writerow([0, 0., 1, "Left", "", "observed", ""])
        writer.writerow([20, 2., 1, "Left", "observed", "lost", "unknown"])
    (out/"manifest.json").write_text(json.dumps({"source": {"name": "clip.avi", "sha256": sha256(Path(args.video)),
                                                            "width": 160, "height": 90}, "parameters": vars(args)},
                                                default=str))
    metrics = {"processed_frames": N, "frames_with_observed_hands": 30}
    (out/"metrics.json").write_text(json.dumps(metrics))
    (out/"COMPLETE").touch()
    return metrics


class ApiTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        cls.media = root/"media"
        cls.media.mkdir()
        cls.video_path = make_video(cls.media)
        (root/"outside.avi").write_bytes(cls.video_path.read_bytes())
        cls.settings = override_settings(MEDIA_ROOTS=[cls.media.resolve()], RUNS_DIR=root/"runs",
                                         DATA_DIR=root/"data", UPLOAD_DIR=cls.media/"uploads", API_TOKEN="",
                                         GOVERNANCE_FILE="", MODEL_PATH=root/"model.task")
        cls.settings.enable()

    @classmethod
    def tearDownClass(cls):
        cls.settings.disable()
        cls.tmp.cleanup()
        super().tearDownClass()

    def post(self, url, data):
        return self.client.post(url, json.dumps(data), content_type="application/json")

    def make_complete_run(self):
        video = self.post("/api/videos", {"path": str(self.video_path)}).json()
        run_id = self.post("/api/runs", {"video_id": video["id"], "preset": "recall", "duration_s": 4}).json()["id"]
        run = jobs.claim_next()
        self.assertEqual(str(run.id), run_id)
        finished = jobs.run_one(run, process=fake_process)
        self.assertEqual(finished.status, "complete", finished.error)
        return run_id, video

    def test_health_presets_and_path_allow_list(self):
        self.assertEqual(self.client.get("/api/health").json()["status"], "ok")
        self.assertIn("recall", self.client.get("/api/presets").json()["presets"])
        outside = Path(self.tmp.name)/"outside.avi"
        self.assertEqual(self.post("/api/videos", {"path": str(outside)}).status_code, 403)
        traversal = str(self.media/".."/"outside.avi")
        self.assertEqual(self.post("/api/videos", {"path": traversal}).status_code, 403)
        first = self.post("/api/videos", {"path": str(self.video_path)})
        self.assertEqual(first.status_code, 201)
        self.assertEqual(first.json()["frame_count"], N)
        again = self.post("/api/videos", {"path": str(self.video_path)}).json()
        self.assertEqual(again["id"], first.json()["id"])

    def test_run_validation_and_cancel(self):
        video = self.post("/api/videos", {"path": str(self.video_path)}).json()
        self.assertEqual(self.post("/api/runs", {"video_id": video["id"], "preset": "fast"}).status_code, 400)
        self.assertEqual(self.post("/api/runs", {"video_id": video["id"], "start_s": 99}).status_code, 400)
        self.assertEqual(self.post("/api/runs", {"video_id": 999}).status_code, 404)
        run = self.post("/api/runs", {"video_id": video["id"]}).json()
        self.assertEqual(run["status"], "queued")
        self.assertEqual(self.client.get(f"/api/runs/{run['id']}/frames").status_code, 409)
        self.assertEqual(self.post(f"/api/runs/{run['id']}/cancel", {}).json()["status"], "cancelled")
        self.assertIsNone(jobs.claim_next())

    def test_job_flow_frames_tracks_and_events(self):
        run_id, _ = self.make_complete_run()
        detail = self.client.get(f"/api/runs/{run_id}").json()
        self.assertEqual((detail["status"], detail["progress"]), ("complete", 1.0))
        self.assertIsNotNone(detail["quality_summary"])
        self.assertEqual(detail["proxy"]["frames"], N)
        self.assertEqual(detail["artifacts"]["identity"], "identity.json")
        page = self.client.get(f"/api/runs/{run_id}/frames?start_s=1.0&end_s=2.5").json()
        self.assertEqual([f["frame_index"] for f in page["frames"]], list(range(10, 25)))
        hand = page["frames"][0]["hands"][0]
        self.assertNotIn("image_xyz_raw", hand)  # lite payload
        self.assertIn("image_xyz", hand)
        paged = self.client.get(f"/api/runs/{run_id}/frames?max_frames=8").json()
        self.assertTrue(paged["truncated"])
        self.assertAlmostEqual(paged["next_start_s"], .8)
        full = self.client.get(f"/api/runs/{run_id}/frames/25").json()
        self.assertEqual(full["hands"][0]["state"], "lost")
        self.assertIsNone(full["hands"][0]["world_xyz_m_raw"])
        self.assertEqual(self.client.get(f"/api/runs/{run_id}/frames/999").status_code, 404)
        tracks = self.client.get(f"/api/runs/{run_id}/tracks").json()["tracks"]
        self.assertEqual([t["track_id"] for t in tracks], [1, 2])
        states = [s["state"] for s in tracks[0]["segments"]]
        self.assertEqual(states[:3], ["observed", "lost", "observed"])  # flicker in 1-2 s
        self.assertEqual(tracks[0]["segments"][-1]["state"], "lost")
        self.assertEqual(tracks[0]["segments"][0]["frames"], 11)  # frames 0-10 observed
        events = self.client.get(f"/api/runs/{run_id}/events?start_s=1").json()["events"]
        self.assertEqual(events[0]["to_state"], "lost")

    def test_quality_review_decisions_and_stats(self):
        run_id, _ = self.make_complete_run()
        quality = self.client.get(f"/api/runs/{run_id}/quality").json()
        self.assertIn("windows", quality)
        items = self.client.get(f"/api/runs/{run_id}/review-queue").json()["items"]
        flagged = [i for i in items if i["status"] == "needs_review"]
        self.assertTrue(flagged)
        item = flagged[0]["item_id"]
        url = f"/api/runs/{run_id}/review-queue/{item}/decisions"
        self.assertEqual(self.post(url, {"verdict": "maybe", "reviewer": "UB"}).status_code, 400)
        self.assertEqual(self.post(url, {"verdict": "false_alarm", "reviewer": ""}).status_code, 400)
        self.assertEqual(self.post(url, {"verdict": "false_alarm", "reviewer": "UB"}).status_code, 201)
        self.assertEqual(self.post(url, {"verdict": "confirmed_issue", "reviewer": "UB"}).status_code, 201)
        stats = self.client.get(f"/api/runs/{run_id}/review-stats").json()
        self.assertEqual((stats["reviewed_items"], stats["confirmed_issue"], stats["flag_precision"]), (1, 1, 1.0))
        self.assertEqual(self.post(f"/api/runs/{run_id}/review-queue/Q9999/decisions",
                                   {"verdict": "false_alarm", "reviewer": "UB"}).status_code, 404)

    def test_preview_range_and_artifact_whitelist(self):
        run_id, _ = self.make_complete_run()
        self.assertEqual(self.client.get(f"/api/runs/{run_id}/preview.mp4").status_code, 409)
        out_dir = Path(Run.objects.get(pk=run_id).out_dir)
        (out_dir/"preview.mp4").write_bytes(bytes(range(256))*4)
        partial = self.client.get(f"/api/runs/{run_id}/preview.mp4", HTTP_RANGE="bytes=10-19")
        self.assertEqual(partial.status_code, 206)
        self.assertEqual(partial["Content-Range"], "bytes 10-19/1024")
        self.assertEqual(b"".join(partial.streaming_content), bytes(range(10, 20)))
        tail = self.client.get(f"/api/runs/{run_id}/preview.mp4", HTTP_RANGE="bytes=-4")
        self.assertEqual(b"".join(tail.streaming_content), bytes(range(252, 256)))
        self.assertEqual(self.client.get(f"/api/runs/{run_id}/preview.mp4", HTTP_RANGE="bytes=5000-").status_code, 416)
        artifact = self.client.get(f"/api/runs/{run_id}/artifacts/landmarks.jsonl")
        self.assertEqual(artifact.status_code, 200)
        artifact.close()
        self.assertEqual(self.client.get(f"/api/runs/{run_id}/artifacts/../../etc/passwd").status_code, 404)

    def test_frame_jpeg_is_the_exact_requested_frame(self):
        video = self.post("/api/videos", {"path": str(self.video_path)}).json()
        for index in (0, 17, 39):
            response = self.client.get(f"/api/videos/{video['id']}/frames/{index}.jpg?width=64")
            self.assertEqual(response.status_code, 200)
            image = cv2.imdecode(np.frombuffer(b"".join(response.streaming_content), np.uint8), cv2.IMREAD_GRAYSCALE)
            self.assertLess(abs(float(image.mean()) - 6*index), 4, f"frame {index}")
        self.assertEqual(self.client.get(f"/api/videos/{video['id']}/frames/40.jpg").status_code, 404)

    def test_proxy_is_frame_exact_for_offset_runs(self):
        video = self.post("/api/videos", {"path": str(self.video_path)}).json()
        run_id = self.post("/api/runs", {"video_id": video["id"], "start_s": 1.0, "duration_s": 2.0}).json()["id"]
        run = jobs.run_one(jobs.claim_next(), process=fake_process)
        self.assertEqual(run.status, "complete", run.error)
        proxy = json.loads((Path(run.out_dir)/"proxy.json").read_text())
        self.assertEqual((proxy["frames"], proxy["time_offset_s"]), (20, 1.0))
        response = self.client.get(f"/api/runs/{run_id}/proxy.mp4", HTTP_RANGE="bytes=0-99")
        self.assertEqual(response.status_code, 206)
        cap = cv2.VideoCapture(str(Path(run.out_dir)/"proxy.mp4"))
        means = []
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            means.append(float(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).mean()))
        cap.release()
        expected = [6*i for i in range(10, 30)]  # source frames 10..29
        self.assertEqual(len(means), 20)
        self.assertLess(max(abs(m - e) for m, e in zip(means, expected)), 4)
        image = self.client.get(f"/api/runs/{run_id}/compare.jpg?t=1.0")
        self.assertEqual((image.status_code, image["Content-Type"]), (200, "image/jpeg"))
        image.close()
        self.assertEqual(self.client.get(f"/api/runs/{run_id}/compare.jpg?t=2.5").status_code, 404)  # no hand

    def test_cancel_during_late_stage_is_not_overwritten_and_delete_waits(self):
        video = self.post("/api/videos", {"path": str(self.video_path)}).json()
        run_id = self.post("/api/runs", {"video_id": video["id"], "duration_s": 4}).json()["id"]
        run = jobs.claim_next()

        def cancel_at_end(args, progress=None, workers=1):
            metrics = fake_process(args)
            self.assertEqual(self.post(f"/api/runs/{run_id}/cancel", {}).json()["status"], "cancelled")
            self.assertEqual(self.client.delete(f"/api/runs/{run_id}").status_code, 409)  # worker still holds it
            return metrics
        finished = jobs.run_one(run, process=cancel_at_end)
        self.assertEqual((finished.status, finished.stage), ("cancelled", "cancelled"))
        self.assertIsNotNone(finished.finished_at)
        self.assertEqual(self.client.delete(f"/api/runs/{run_id}").status_code, 204)

    def test_recover_only_touches_runs_of_dead_workers(self):
        import os
        import socket
        video = self.post("/api/videos", {"path": str(self.video_path)}).json()
        live = Run.objects.create(video_id=video["id"], status="running", worker_id=f"{socket.gethostname()}:{os.getpid()}")
        dead = Run.objects.create(video_id=video["id"], status="running", worker_id=f"{socket.gethostname()}:999999")
        remote = Run.objects.create(video_id=video["id"], status="running", worker_id="other-host:1")
        self.assertEqual(jobs.recover_stale(), 1)
        statuses = {r.pk: r.status for r in Run.objects.all()}
        self.assertEqual((statuses[live.pk], statuses[dead.pk], statuses[remote.pk]), ("running", "failed", "running"))

    def test_bad_inputs_are_json_400_and_ranges_are_not_gzipped(self):
        video = self.post("/api/videos", {"path": str(self.video_path)}).json()
        for payload in ({"video_id": "abc"}, {"video_id": video["id"], "start_s": ""},
                        {"video_id": video["id"], "workers": "x"}, {"video_id": video["id"], "duration_s": "NaN"},
                        {"video_id": video["id"], "workers": True}):
            response = self.post("/api/runs", payload)
            self.assertEqual(response.status_code, 400, payload)
            self.assertIn("error", response.json())
        run_id, _ = self.make_complete_run()
        empty = self.client.get(f"/api/runs/{run_id}/proxy.mp4", HTTP_RANGE="bytes=-")
        self.assertEqual(empty.status_code, 416)
        ranged = self.client.get(f"/api/runs/{run_id}/proxy.mp4", HTTP_RANGE="bytes=0-99", HTTP_ACCEPT_ENCODING="gzip")
        self.assertEqual(ranged.status_code, 206)
        self.assertNotIn("Content-Encoding", ranged)
        frames = self.client.get(f"/api/runs/{run_id}/frames", HTTP_ACCEPT_ENCODING="gzip")
        self.assertEqual(frames["Content-Encoding"], "gzip")
        self.assertEqual(self.client.get(f"/api/runs/{run_id}/frames/999").json()["error"],
                         "frame 999 was not processed in this run")

    def test_failed_job_records_error(self):
        video = self.post("/api/videos", {"path": str(self.video_path)}).json()
        self.post("/api/runs", {"video_id": video["id"]})

        def broken(args, progress=None, workers=1):
            raise RuntimeError("decoder exploded")
        run = jobs.run_one(jobs.claim_next(), process=broken)
        self.assertEqual(run.status, "failed")
        self.assertIn("decoder exploded", run.error)


class SecurityTests(TestCase):
    @override_settings(API_TOKEN="s3cret", CORS_ALLOWED_ORIGINS=["http://localhost:5173"])
    def test_token_and_cors(self):
        self.assertEqual(self.client.get("/api/health").status_code, 200)  # health stays open
        self.assertEqual(self.client.get("/api/videos").status_code, 401)
        self.assertEqual(self.client.get("/api/videos", HTTP_AUTHORIZATION="Bearer wrong").status_code, 401)
        ok = self.client.get("/api/videos", HTTP_AUTHORIZATION="Bearer s3cret", HTTP_ORIGIN="http://localhost:5173")
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok["Access-Control-Allow-Origin"], "http://localhost:5173")
        self.assertEqual(self.client.get("/api/videos?token=s3cret").status_code, 200)  # for <video src>
        other = self.client.get("/api/health", HTTP_ORIGIN="http://evil.example")
        self.assertNotIn("Access-Control-Allow-Origin", other)
        preflight = self.client.options("/api/videos", HTTP_ORIGIN="http://localhost:5173")
        self.assertEqual(preflight.status_code, 204)
