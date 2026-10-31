import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from api.services import allowed_media_path
from api.views import register_video


class Command(BaseCommand):
    help = "Register a video file (under EGOHAND_MEDIA_ROOTS) without running the server."

    def add_arguments(self, parser):
        parser.add_argument("path")

    def handle(self, *args, **options):
        try:
            video = register_video(allowed_media_path(Path(options["path"])))
        except (PermissionError, FileNotFoundError) as error:
            raise CommandError(str(error))
        self.stdout.write(json.dumps({"id": video.id, "name": video.name, "frames": video.frame_count}))
