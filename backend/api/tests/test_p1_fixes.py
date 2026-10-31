"""Regression tests for browser writes, run deletion, and stale-worker recovery."""
from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone

from api import jobs
from api.models import ReviewDecision, Run, Video


class P1FixTests(TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[3])
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        settings = override_settings(
            RUNS_DIR=self.root/"runs", UPLOAD_DIR=self.root/"uploads",
            MEDIA_ROOTS=[self.root], API_TOKEN="",
            CORS_ALLOWED_ORIGINS=["http://localhost:5173"],
        )
        settings.enable()
        self.addCleanup(settings.disable)
        self.video = Video.objects.create(
            name="clip.mp4", path=str(self.root/"clip.mp4"), sha256="0" * 64,
            width=160, height=90, fps=10, frame_count=40, duration_s=4,
            timestamp_source="test",
        )

    def post_json(self, path, payload, **headers):
        return self.client.post(path, json.dumps(payload), content_type="application/json", **headers)

    def finished_run(self):
        run = Run.objects.create(video=self.video, status=Run.Status.COMPLETE, finished_at=timezone.now())
        output = self.root/"runs"/str(run.id)
        output.mkdir(parents=True)
        run.out_dir = str(output)
        run.save(update_fields=["out_dir"])
        return run, output

    def test_untrusted_browser_origins_block_every_mutation(self):
        run, output = self.finished_run()
        quality = output/"quality"
        quality.mkdir()
        (quality/"review_queue.json").write_text(json.dumps([{"item_id": "Q1"}]))
        queued = Run.objects.create(video=self.video)
        requests = [
            lambda headers: self.post_json("/api/runs", {"video_id": self.video.pk}, **headers),
            lambda headers: self.client.post("/api/videos/upload", {"file": SimpleUploadedFile("clip.mp4", b"video")}, **headers),
            lambda headers: self.client.delete(f"/api/runs/{run.pk}", **headers),
            lambda headers: self.post_json(f"/api/runs/{run.pk}/review-queue/Q1/decisions",
                                           {"verdict": "confirmed_issue", "reviewer": "UB"}, **headers),
            lambda headers: self.post_json(f"/api/runs/{queued.pk}/cancel", {}, **headers),
        ]
        for headers in ({"HTTP_ORIGIN": "http://evil.example"}, {"HTTP_ORIGIN": "null"},
                        {"HTTP_SEC_FETCH_SITE": "cross-site"}, {"HTTP_SEC_FETCH_SITE": "same-site"}):
            for request in requests:
                with self.subTest(headers=headers, request=request):
                    self.assertEqual(request(headers).status_code, 403)
        self.assertEqual(Run.objects.count(), 2)
        self.assertTrue(output.exists())
        self.assertEqual(ReviewDecision.objects.count(), 0)
        queued.refresh_from_db()
        self.assertEqual(queued.status, Run.Status.QUEUED)

    def test_same_origin_trusted_cors_and_cli_can_create_jobs(self):
        for headers in ({"HTTP_ORIGIN": "http://testserver"},
                        {"HTTP_ORIGIN": "http://localhost:5173"}, {}):
            with self.subTest(headers=headers):
                response = self.post_json("/api/runs", {"video_id": self.video.pk}, **headers)
                self.assertEqual(response.status_code, 202)
        self.assertEqual(Run.objects.count(), 3)

    def test_null_origin_is_never_trusted(self):
        with override_settings(CORS_ALLOWED_ORIGINS=["null"]):
            response = self.post_json("/api/runs", {"video_id": self.video.pk}, HTTP_ORIGIN="null")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Run.objects.count(), 0)

    def test_json_content_type_required_but_charset_accepted(self):
        data = json.dumps({"video_id": self.video.pk})
        self.assertEqual(self.client.post("/api/runs", data, content_type="text/plain").status_code, 415)
        self.assertEqual(self.client.post("/api/runs", data, content_type="application/json; charset=utf-8").status_code, 202)
        self.assertEqual(Run.objects.count(), 1)

    def test_token_and_preflight_still_work(self):
        with override_settings(API_TOKEN="secret"):
            self.assertEqual(self.post_json("/api/runs", {"video_id": self.video.pk}).status_code, 401)
            response = self.post_json("/api/runs", {"video_id": self.video.pk},
                                      HTTP_ORIGIN="http://localhost:5173", HTTP_AUTHORIZATION="Bearer secret")
            self.assertEqual(response.status_code, 202)
            preflight = self.client.options("/api/runs", HTTP_ORIGIN="http://localhost:5173")
            self.assertEqual(preflight.status_code, 204)
            self.assertEqual(preflight["Access-Control-Allow-Origin"], "http://localhost:5173")

    def test_locked_output_preserves_record_and_can_retry(self):
        run, output = self.finished_run()
        (output/"locked.mp4").write_bytes(b"data")
        with patch("api.views.shutil.rmtree", side_effect=PermissionError("file is open")):
            response = self.client.delete(f"/api/runs/{run.pk}")
        self.assertEqual(response.status_code, 503)
        self.assertIn("retry", response.json()["error"])
        self.assertTrue(Run.objects.filter(pk=run.pk).exists())
        self.assertTrue((output/"locked.mp4").exists())
        self.assertEqual(self.client.delete(f"/api/runs/{run.pk}").status_code, 204)
        self.assertFalse(Run.objects.filter(pk=run.pk).exists())
        self.assertFalse(output.exists())

    def test_missing_output_and_unsafe_output_paths(self):
        run, output = self.finished_run()
        output.rmdir()
        self.assertEqual(self.client.delete(f"/api/runs/{run.pk}").status_code, 204)
        run, output = self.finished_run()
        other = self.root/"other"
        other.mkdir()
        (other/"keep").touch()
        run.out_dir = str(other)
        run.save(update_fields=["out_dir"])
        self.assertEqual(self.client.delete(f"/api/runs/{run.pk}").status_code, 409)
        self.assertTrue(Run.objects.filter(pk=run.pk).exists())
        self.assertTrue((other/"keep").exists())

    def test_missing_nested_file_does_not_drop_record_if_directory_remains(self):
        run, output = self.finished_run()
        with patch("api.views.shutil.rmtree", side_effect=FileNotFoundError("child disappeared")):
            response = self.client.delete(f"/api/runs/{run.pk}")
        self.assertEqual(response.status_code, 503)
        self.assertTrue(Run.objects.filter(pk=run.pk).exists())
        self.assertTrue(output.exists())

    def test_process_liveness_uses_windows_safe_pid_check(self):
        host = socket.gethostname()
        process = subprocess.Popen([sys.executable, "-c", "pass"])
        process.wait(timeout=10)
        with patch.object(jobs.os, "kill", side_effect=AssertionError("os.kill must not be called")):
            self.assertFalse(jobs._alive(f"{host}:{process.pid}"))
            self.assertTrue(jobs._alive(f"{host}:{os.getpid()}"))
            self.assertTrue(jobs._alive("remote-host:1"))
            self.assertTrue(jobs._alive("unknown"))

    def test_recovery_does_not_overwrite_concurrent_cancellation(self):
        run = Run.objects.create(video=self.video, status=Run.Status.RUNNING, worker_id="dead:1")

        def cancel_during_probe(_worker_id):
            Run.objects.filter(pk=run.pk).update(status=Run.Status.CANCELLED)
            return False

        with patch.object(jobs, "_alive", side_effect=cancel_during_probe):
            self.assertEqual(jobs.recover_stale(), 0)
        run.refresh_from_db()
        self.assertEqual(run.status, Run.Status.CANCELLED)
        self.assertIsNotNone(run.finished_at)
        self.assertEqual(run.stage, "cancelled")
