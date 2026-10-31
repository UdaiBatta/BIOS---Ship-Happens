from django.core.management.base import BaseCommand

from api.jobs import recover_stale, work_forever


class Command(BaseCommand):
    help = "Process queued EgoHand Twin runs (one at a time per worker process)."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Process at most one run, then exit")
        parser.add_argument("--poll", type=float, default=1., help="Seconds between queue checks")
        parser.add_argument("--recover", action="store_true",
                            help="Mark runs left 'running' by a crashed worker as failed before starting")

    def handle(self, *args, **options):
        if options["recover"]:
            self.stdout.write(f"Recovered {recover_stale()} stale run(s)")
        work_forever(options["poll"], options["once"])
