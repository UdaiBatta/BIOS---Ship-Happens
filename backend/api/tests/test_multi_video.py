"""Several distinct source videos: discovery while running, repeated processing, bad inputs, recovery."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile

import cv2
import numpy as np
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from api import jobs
from api.models import Run, Video
from api.tests.test_api import fake_process


def write_mp4(path: Path, frames: int, shade: int, size=(160, 96)) -> Path:
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10, size)
    for i in range(frames):
        writer.write(np.full((size[1], size[0], 3), (shade + 3*i) % 255, np.uint8))
    writer.release()
    return path


class MultiVideoTests(TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.media = self.root/"media"
        (self.media/"Sample").mkdir(parents=True)
        settings = override_settings(MEDIA_ROOTS=[self.media.resolve()], RUNS_DIR=self.root/"runs",
                                     DATA_DIR=self.root/"data", UPLOAD_DIR=self.root/"uploads", API_TOKEN="",
                                     GOVERNANCE_FILE="", MODEL_PATH=self.root/"model.task", LIFT_HFOV=None)
        settings.enable()
        self.addCleanup(settings.disable)

    def post(self, url, data=None):
        return self.client.post(url, json.dumps(data or {}), content_type="application/json")

    def test_videos_added_while_running_are_found_by_scan_and_listed(self):
        write_mp4(self.media/"Sample"/"a.mp4", 30, 10)
        first = self.post("/api/videos/scan").json()
        self.assertEqual([v["name"] for v in first["registered"]], ["Sample/a.mp4"])
        write_mp4(self.media/"Sample"/"b.mp4", 50, 120, size=(192, 108))      # added later, different file
        (self.media/"Sample"/"notes.txt").write_text("not a video")
        (self.media/"Sample"/"bad.mp4").write_bytes(b"not a video either")
        second = self.post("/api/videos/scan").json()
        self.assertEqual([v["name"] for v in second["registered"]], ["Sample/b.mp4"])
        self.assertEqual(second["already_registered"], 1)
        self.assertEqual([f["name"] for f in second["failed"]], ["bad.mp4"])
        listed = {v["name"]: v for v in self.client.get("/api/videos").json()["videos"]}
        self.assertEqual(set(listed), {"Sample/a.mp4", "Sample/b.mp4"})
        self.assertNotEqual(listed["Sample/a.mp4"]["sha256"], listed["Sample/b.mp4"]["sha256"])
        self.assertEqual((listed["Sample/a.mp4"]["frame_count"], listed["Sample/b.mp4"]["frame_count"]), (30, 50))

    def test_each_video_processes_and_runs_stay_bound_to_their_video(self):
        for name, n in (("a.mp4", 30), ("b.mp4", 50)):
            write_mp4(self.media/"Sample"/name, n, 40)
        self.post("/api/videos/scan")
        ids = {v.name: v.id for v in Video.objects.all()}
        runs = [self.post("/api/runs", {"video_id": ids[name], "preset": "recall", "start_s": 0, "duration_s": 2}).json()
                for name in ("Sample/a.mp4", "Sample/b.mp4", "Sample/a.mp4")]        # a.mp4 processed twice
        for _ in runs:
            jobs.run_one(jobs.claim_next(), process=fake_process)
        done = {r["id"]: self.client.get(f"/api/runs/{r['id']}").json() for r in runs}
        self.assertTrue(all(d["status"] == "complete" for d in done.values()), [d["error"] for d in done.values()])
        self.assertEqual([done[r["id"]]["video"]["name"] for r in runs], ["Sample/a.mp4", "Sample/b.mp4", "Sample/a.mp4"])
        self.assertEqual(len({d["id"] for d in done.values()}), 3)               # repeated runs do not collide
        listed = self.client.get(f"/api/runs?status=complete&video_id={ids['Sample/b.mp4']}").json()["runs"]
        self.assertEqual([r["id"] for r in listed], [runs[1]["id"]])

    def test_invalid_paths_and_unsupported_files_are_refused_clearly(self):
        outside = write_mp4(self.root/"outside.mp4", 10, 5)
        self.assertEqual(self.post("/api/videos", {"path": str(outside)}).status_code, 403)
        self.assertEqual(self.post("/api/videos", {"path": str(self.media/"missing.mp4")}).status_code, 404)
        self.assertEqual(self.post("/api/videos", {"path": str(self.media/".."/"outside.mp4")}).status_code, 403)
        bad = SimpleUploadedFile("clip.exe", b"MZ", content_type="application/octet-stream")
        self.assertEqual(self.client.post("/api/videos/upload", {"file": bad}).status_code, 400)
        fake = SimpleUploadedFile("clip.mp4", b"not a video", content_type="video/mp4")
        response = self.client.post("/api/videos/upload", {"file": fake})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(any((self.root/"uploads").glob("*.mp4")))                # rejected upload removed

    def test_a_failed_run_does_not_block_the_next(self):
        write_mp4(self.media/"Sample"/"a.mp4", 30, 10)
        self.post("/api/videos/scan")
        vid = Video.objects.get().id
        bad = self.post("/api/runs", {"video_id": vid, "duration_s": 2}).json()
        good = self.post("/api/runs", {"video_id": vid, "duration_s": 2}).json()

        def broken(args, progress=None, workers=1):
            raise RuntimeError("decoder crashed")
        jobs.run_one(jobs.claim_next(), process=broken)
        jobs.run_one(jobs.claim_next(), process=fake_process)
        self.assertEqual(Run.objects.get(pk=bad["id"]).status, "failed")
        self.assertIn("decoder crashed", Run.objects.get(pk=bad["id"]).error)
        self.assertEqual(Run.objects.get(pk=good["id"]).status, "complete")

    def test_segment_beyond_the_source_is_refused_and_durations_are_reported(self):
        write_mp4(self.media/"Sample"/"a.mp4", 30, 10)                             # 3 s at 10 fps
        self.post("/api/videos/scan")
        video = self.client.get("/api/videos").json()["videos"][0]
        self.assertAlmostEqual(video["duration_s"], 2.9, places=1)
        self.assertEqual(self.post("/api/runs", {"video_id": video["id"], "start_s": 5}).status_code, 400)
        run = self.post("/api/runs", {"video_id": video["id"], "start_s": 1, "duration_s": 60}).json()
        self.assertEqual((run["start_s"], run["duration_s"]), (1., 60.))           # clipped at the source end in processing

    def test_moved_file_is_flagged_and_unreadable_file_explained(self):
        clip = write_mp4(self.media/"Sample"/"a.mp4", 30, 10)
        (self.media/"Sample"/"bad.mp4").write_bytes(b"x")
        report = self.post("/api/videos/scan").json()
        self.assertEqual(report["failed"][0]["error"], "not a readable video (FFprobe could not open it)")
        clip.unlink()
        video = self.client.get("/api/videos").json()["videos"][0]
        self.assertFalse(video["available"])
        self.assertEqual(self.post("/api/runs", {"video_id": video["id"]}).status_code, 404)
