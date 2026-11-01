"""egohand_register accepts a folder and registers every video in it, skipping bad files."""
from __future__ import annotations

from io import StringIO
from pathlib import Path
import shutil
import tempfile
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from api.models import Video
from api.tests.test_api import make_video


class RegisterFolderTests(TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.media = root/"media"
        (self.media/"day2").mkdir(parents=True)
        first = make_video(self.media)
        shutil.copy(first, self.media/"day2"/"second.avi")
        (self.media/"day2"/"notes.txt").write_text("not a video")
        (self.media/"broken.mp4").write_bytes(b"not really a video")
        self.outside = root/"outside.avi"
        shutil.copy(first, self.outside)
        settings = override_settings(MEDIA_ROOTS=[self.media.resolve()], UPLOAD_DIR=root/"uploads")
        settings.enable()
        self.addCleanup(settings.disable)

    def register(self, *paths):
        out, err = StringIO(), StringIO()
        call_command("egohand_register", *map(str, paths), stdout=out, stderr=err)
        return out.getvalue(), err.getvalue()

    def test_folder_registers_every_video_recursively_and_skips_bad_files(self):
        out, err = self.register(self.media)
        # Names are relative to the media folder, so same-named files in subfolders stay distinct.
        self.assertEqual(sorted(Video.objects.values_list("name", flat=True)), ["clip.avi", "day2/second.avi"])
        self.assertIn("broken.mp4", err)
        self.assertNotIn("notes.txt", out + err)
        # Running again is idempotent and skips the re-hash of registered files.
        with patch("api.views.sha256") as rehash:
            out, _ = self.register(self.media)
        # Only the never-registered broken file is tried again.
        self.assertEqual([call.args[0].name for call in rehash.call_args_list], ["broken.mp4"])
        self.assertIn("\"already_registered\": 2", out)
        self.assertEqual(Video.objects.count(), 2)

    def test_files_outside_the_allowed_folders_are_refused(self):
        with self.assertRaises(CommandError):
            self.register(self.outside)
        self.assertEqual(Video.objects.count(), 0)

    def test_queueing_a_run_requires_video_id(self):
        response = self.client.post("/api/runs", "{}", content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("video_id is required", response.json()["error"])

    def test_hybrid_preset_is_hidden_and_refused_without_its_models(self):
        with override_settings(RTM_MODELS=Path(tempfile.gettempdir())/"no-rtm-models-here"):
            presets = self.client.get("/api/presets").json()["presets"]
            self.assertNotIn("hybrid", presets)
            self.assertIn("accurate", presets)
            video = Video.objects.create(name="v", path="/x/v.mp4", sha256="0"*64, width=10, height=10,
                                         fps=30, frame_count=3, duration_s=.1, timestamp_source="t")
            response = self.client.post("/api/runs", '{"video_id": %d, "preset": "hybrid"}' % video.id,
                                        content_type="application/json")
            self.assertEqual(response.status_code, 400)
            self.assertIn("fetch-model --rtm", response.json()["error"])
