import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from api.views import VIDEO_SUFFIXES, scan_media  # noqa: F401  (VIDEO_SUFFIXES re-exported)


class Command(BaseCommand):
    help = ("Register a video file, or every video in a folder (recursively), without running the server. "
            "Paths must be under EGOHAND_MEDIA_ROOTS. Already registered, unchanged files are skipped.")

    def add_arguments(self, parser):
        parser.add_argument("paths", nargs="+")

    def handle(self, *args, **options):
        for raw in options["paths"]:
            if Path(raw).is_dir() and not any(p.suffix.lower() in VIDEO_SUFFIXES for p in Path(raw).rglob("*")):
                self.stderr.write(f"No video files in {raw}")
        report = scan_media(options["paths"])
        for video in report["registered"]:
            self.stdout.write(json.dumps({"id": video["id"], "name": video["name"], "frames": video["frame_count"]}))
        if report["already_registered"]:
            self.stdout.write(json.dumps({"already_registered": report["already_registered"]}))
        for failure in report["failed"]:
            self.stderr.write(f"Not registered: {failure['name']}: {failure['error']}")
        if report["failed"] and not report["registered"] and not report["already_registered"]:
            raise CommandError(f"No video registered ({len(report['failed'])} failed)")
