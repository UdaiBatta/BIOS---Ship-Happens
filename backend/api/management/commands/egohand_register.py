import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from api.models import Video
from api.services import allowed_media_path
from api.views import register_video

VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".avi", ".m4v", ".webm"}


class Command(BaseCommand):
    help = ("Register a video file, or every video in a folder (recursively), without running the server. "
            "Paths must be under EGOHAND_MEDIA_ROOTS. Already registered, unchanged files are skipped.")

    def add_arguments(self, parser):
        parser.add_argument("paths", nargs="+")

    def handle(self, *args, **options):
        files, failures = [], 0
        for raw in options["paths"]:
            path = Path(raw)
            if path.is_dir():
                found = sorted(p for p in path.rglob("*") if p.is_file() and p.suffix.lower() in VIDEO_SUFFIXES)
                if not found:
                    self.stderr.write(f"No video files in {path}")
                files.extend(found)
            else:
                files.append(path)
        for path in files:
            try:
                resolved = allowed_media_path(path)
                video = Video.objects.filter(path=str(resolved)).first()
                if video is not None:
                    # Already registered: skip the full re-hash on every launch. Processing still
                    # verifies the SHA-256 before a run is queued and again in the worker.
                    self.stdout.write(json.dumps({"id": video.id, "name": video.name, "frames": video.frame_count,
                                                  "status": "already registered"}))
                    continue
                video = register_video(resolved)
            except Exception as error:  # outside the allowed folders, changed, unreadable or corrupt: skip it
                failures += 1
                self.stderr.write(f"Not registered: {path.name}: {error}")
                continue
            self.stdout.write(json.dumps({"id": video.id, "name": video.name, "frames": video.frame_count}))
        if failures and failures == len(files):
            raise CommandError(f"No video registered ({failures} failed)")
