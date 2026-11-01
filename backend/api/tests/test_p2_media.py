"""PR2 media integrity, validation, and frame-exact proxy regressions."""
from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
from unittest.mock import patch

import cv2
import numpy as np
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from api import jobs, services
from api.models import Run, Video
from motioniq.pipeline import probe
from api.tests.test_api import make_video


class MediaRegressionTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.media = cls.root / "configured-media"
        cls.media.mkdir()
        cls.uploads = cls.root / "external-upload-dir"
        cls.uploads.mkdir()
        cls.video = make_video(cls.media)
        cls.settings = override_settings(MEDIA_ROOTS=[cls.media], UPLOAD_DIR=cls.uploads,
                                         RUNS_DIR=cls.root / "runs", DATA_DIR=cls.root / "data",
                                         API_TOKEN="", MODEL_PATH=cls.root / "model.task", LIFT_HFOV=None,
                                         GOVERNANCE_FILE="")
        cls.settings.enable()

    @classmethod
    def tearDownClass(cls):
        cls.settings.disable()
        cls.tmp.cleanup()
        super().tearDownClass()

    def post(self, url, payload):
        import json
        return self.client.post(url, json.dumps(payload), content_type="application/json")

    def test_upload_directory_is_allowed_outside_configured_media_roots(self):
        uploaded = SimpleUploadedFile("submitted.avi", self.video.read_bytes(), content_type="video/x-msvideo")
        response = self.client.post("/api/videos/upload", {"file": uploaded})
        self.assertEqual(response.status_code, 201, response.content)
        path = Path(response.json()["name"])
        self.assertTrue((self.uploads / path.name).is_file())
        self.assertEqual(services.allowed_media_path(self.uploads / path.name), (self.uploads / path.name).resolve())
        with self.assertRaises(PermissionError):
            services.allowed_media_path(self.root / "other" / "not-allowed.avi")

    def test_changed_registered_source_cannot_be_reused_or_queued(self):
        video = self.post("/api/videos", {"path": str(self.video)}).json()
        changed = bytearray(self.video.read_bytes())
        changed[-1] ^= 1
        self.video.write_bytes(changed)
        response = self.post("/api/videos", {"path": str(self.video)})
        self.assertEqual(response.status_code, 409)
        queued = self.post("/api/runs", {"video_id": video["id"]})
        self.assertEqual(queued.status_code, 409)

    def test_source_changed_after_enqueue_fails_before_processing(self):
        video = self.post("/api/videos", {"path": str(self.video)}).json()
        response = self.post("/api/runs", {"video_id": video["id"]})
        run = jobs.claim_next()
        self.assertEqual(str(run.pk), response.json()["id"])
        changed = bytearray(self.video.read_bytes())
        changed[-1] ^= 1
        self.video.write_bytes(changed)
        finished = jobs.run_one(run, process=lambda *a, **k: self.fail("processed stale source"))
        self.assertEqual(finished.status, Run.Status.FAILED)
        self.assertIn("source video changed", finished.error)

    def test_get_invalid_video_id_is_json_400_and_tail_intervals_are_rejected(self):
        self.assertEqual(self.client.get("/api/runs?video_id=nope").status_code, 400)
        video = self.post("/api/videos", {"path": str(self.video)}).json()
        tail = self.post("/api/runs", {"video_id": video["id"], "start_s": 3.91})
        self.assertEqual(tail.status_code, 400)
        empty = self.post("/api/runs", {"video_id": video["id"], "start_s": 3.89, "duration_s": 0.005})
        self.assertEqual(empty.status_code, 400)

    def test_run_detail_advertises_only_available_endpoint_supported_artifacts(self):
        video_data = self.post("/api/videos", {"path": str(self.video)}).json()
        video = Video.objects.get(pk=video_data["id"])
        out = self.root / "runs" / "contract-test"
        out.mkdir(parents=True)
        run = Run.objects.create(video=video, status=Run.Status.COMPLETE, out_dir=str(out), finished_at=timezone.now())
        details_url = f"/api/runs/{run.pk}"
        self.assertIsNone(self.client.get(details_url).json()["artifacts"]["lift"])
        (out / "proxy.json").write_text('{"path":"proxy.mp4","width":960,"frames":2,"time_offset_s":1.1,'
                                      '"frame_index_range":[8,9],"timestamp_mode":"source_pts"}')
        (out / "identity.json").write_text("{}")
        (out / "lift_hfov120.json").write_text("{}")
        (out / "lift_hfov120.npz").write_bytes(b"npz")
        (out / "lift_hfov1.5.json").write_text("{}")
        (out / "lift_hfov1.5.npz").write_bytes(b"npz")
        (out / "lift_hfov1234.json").write_text("{}")
        (out / "lift_hfov1234.npz").write_bytes(b"npz")
        details = self.client.get(details_url).json()
        self.assertEqual(details["proxy"]["time_offset_s"], 1.1)
        self.assertEqual(details["artifacts"], {"identity": "identity.json",
                                                 "lift": {"summary": "lift_hfov120.json",
                                                          "arrays": "lift_hfov120.npz"},
                                                 "motion_events": None})
        artifact = self.client.get(f"/api/runs/{run.pk}/artifacts/lift_hfov120.json")
        self.assertEqual(artifact.status_code, 200)
        artifact.close()
        self.assertEqual(self.client.get(f"/api/runs/{run.pk}/artifacts/lift_hfov1.5.json").status_code, 404)
        self.assertEqual(self.client.get(f"/api/runs/{run.pk}/artifacts/lift_hfov1234.json").status_code, 404)

    def test_legacy_proxy_is_not_advertised_or_served_as_frame_exact(self):
        video_data = self.post("/api/videos", {"path": str(self.video)}).json()
        video = Video.objects.get(pk=video_data["id"])
        out = self.root / "runs" / "legacy-test"
        out.mkdir(parents=True)
        run = Run.objects.create(video=video, status=Run.Status.COMPLETE, out_dir=str(out), finished_at=timezone.now())
        (out / "proxy.json").write_text('{"path":"proxy.mp4","width":960,"frames":20,"time_offset_s":1.0}')
        (out / "proxy.mp4").write_bytes(b"legacy proxy")
        self.assertIsNone(self.client.get(f"/api/runs/{run.pk}").json()["proxy"])
        response = self.client.get(f"/api/runs/{run.pk}/proxy.mp4")
        self.assertEqual(response.status_code, 409)
        self.assertIn("submit a new run", response.json()["error"])

    def test_proxy_selects_actual_source_frames_for_fractional_start(self):
        source = self.media / "clip.avi"
        output = self.root / "proxy.mp4"
        # start=1.01 selects source frames 11..29 at 10 fps, not an ffmpeg-rounded seek.
        proxy = services.build_proxy(source, output, 11, 29, 1.1)
        self.assertEqual((proxy["frames"], proxy["time_offset_s"]), (19, 1.1))
        cap = cv2.VideoCapture(str(output))
        means = []
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            means.append(float(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).mean()))
        cap.release()
        expected = [6 * i for i in range(11, 30)]
        self.assertEqual(len(means), len(expected))
        self.assertLess(max(abs(actual - target) for actual, target in zip(means, expected)), 4)

    def test_proxy_selects_exact_frames_from_fractional_seek_h264_source(self):
        h264 = self.root / "source-h264.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(self.video), "-c:v", "libx264",
                        "-crf", "0", "-pix_fmt", "yuv420p", str(h264)], check=True,
                       capture_output=True, timeout=60)
        expected_cap = cv2.VideoCapture(str(h264))
        expected = []
        while True:
            ok, frame = expected_cap.read()
            if not ok:
                break
            expected.append(float(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).mean()))
        expected_cap.release()
        output = self.root / "h264-proxy.mp4"
        proxy = services.build_proxy(h264, output, 11, 19, 1.1)
        self.assertEqual(proxy["frames"], 9)
        cap = cv2.VideoCapture(str(output))
        means = []
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            means.append(float(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).mean()))
        cap.release()
        self.assertEqual(len(means), 9)
        self.assertLess(max(abs(a - b) for a, b in zip(means, expected[11:20])), 4)

    def test_proxy_preserves_irregular_source_presentation_timestamps(self):
        source = self.root / "irregular-pts.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(self.video), "-an", "-vf",
                        r"setpts=(N/10+0.017*mod(N\,3))/TB", "-fps_mode", "passthrough",
                        "-enc_time_base:v", "1:1000", "-c:v", "libx264", "-preset", "veryfast",
                        "-crf", "20", "-pix_fmt", "yuv420p", str(source)], check=True,
                       capture_output=True, timeout=60)
        source_times = np.asarray(probe(source)["timestamps"], np.float64)
        output = self.root / "irregular-proxy.mp4"
        proxy = services.build_proxy(source, output, 8, 20, float(source_times[8] - source_times[0]))
        proxy_times = np.asarray(probe(output)["timestamps"], np.float64)
        expected = source_times[8:21] - source_times[8]
        self.assertEqual(proxy["frames"], len(expected))
        self.assertEqual(len(proxy_times), len(expected))
        self.assertLessEqual(float(np.max(np.abs(proxy_times - expected))), 1e-6)

    def test_frame_at_time_uses_presentation_timestamps_and_rejects_invalid_times(self):
        video = self.post("/api/videos", {"path": str(self.video)}).json()
        timestamps = np.r_[0., .08, .4, .47 + np.arange(37)*.1]
        with patch("api.views.services.video_timestamps", return_value=timestamps):
            selected = self.client.get(f"/api/videos/{video['id']}/frame-at?time_s=0.1")
            self.assertEqual(selected.status_code, 200)
            self.assertEqual(selected.json(), {"frame_index": 2, "timestamp_s": .4})
            for value in ("-0.1", "nan", "inf", "4.2"):
                self.assertEqual(self.client.get(f"/api/videos/{video['id']}/frame-at?time_s={value}").status_code, 400)
