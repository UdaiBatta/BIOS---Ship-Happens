"""Database-backed job runner for processing runs (no Redis/Celery needed).

Start one or more workers with ``python manage.py egohand_worker``. Each worker claims
the oldest queued run with an atomic conditional UPDATE, so two workers never process
the same run. MediaPipe inference is CPU-bound: run about one worker per two cores, or
one worker with ``workers>1`` per run for parallel chunked detection.

Stages: processing (0-0.85) -> quality (0.9) -> indexing (0.97) -> complete.
Cancelling a running job is checked at every progress callback.
"""
from __future__ import annotations

import logging
from pathlib import Path
import time
import traceback

from django.conf import settings
from django.db import close_old_connections
from django.utils import timezone

from .models import Run
from .services import build_frame_index, build_tracks

log = logging.getLogger(__name__)


class Cancelled(Exception):
    pass


def claim_next() -> Run | None:
    """Atomically move the oldest queued run to running; None if nothing is queued."""
    for run in Run.objects.filter(status=Run.Status.QUEUED).order_by("created_at")[:5]:
        claimed = Run.objects.filter(pk=run.pk, status=Run.Status.QUEUED).update(
            status=Run.Status.RUNNING, stage="starting", started_at=timezone.now(), progress=0.)
        if claimed:
            return Run.objects.get(pk=run.pk)
    return None


def build_process_argv(run: Run, out_dir: Path) -> list[str]:
    argv = [run.video.path, "--out", str(out_dir), "--model", str(settings.MODEL_PATH), "--preset", run.preset,
            "--start-seconds", str(run.start_s)]
    if run.duration_s:
        argv += ["--duration", str(run.duration_s)]
    if not run.render_preview:
        argv.append("--no-video")
    if run.write_rrd:
        argv.append("--rrd")
    if settings.GOVERNANCE_FILE:
        argv += ["--governance", settings.GOVERNANCE_FILE]
    return argv


def execute(run: Run, process=None) -> None:
    """Run the pipeline for ``run`` and post-process outputs. ``process`` is injectable for tests."""
    from egohand_twin.cli import process_args
    from egohand_twin.quality import write_quality
    if process is None:
        from egohand_twin.parallel import process_parallel
        process = process_parallel
    out_dir = settings.RUNS_DIR/str(run.id)
    Run.objects.filter(pk=run.pk).update(out_dir=str(out_dir), stage="processing")
    last_update = [0.]

    def progress(done: int, expected: int):
        now = time.monotonic()
        if now - last_update[0] < .5 and done < expected:
            return
        last_update[0] = now
        status = Run.objects.filter(pk=run.pk).values_list("status", flat=True).first()
        if status == Run.Status.CANCELLED:
            raise Cancelled()
        Run.objects.filter(pk=run.pk).update(progress=.85*min(1., done/max(expected, 1)))

    args = process_args(build_process_argv(run, out_dir))
    metrics = process(args, progress=progress, workers=run.workers)
    Run.objects.filter(pk=run.pk).update(stage="quality", progress=.9, metrics=metrics)
    summary = write_quality(out_dir, Path(run.video.path))
    Run.objects.filter(pk=run.pk).update(stage="indexing", progress=.97, quality_summary=summary)
    build_frame_index(out_dir)
    build_tracks(out_dir)


def run_one(run: Run, process=None) -> Run:
    try:
        execute(run, process)
        Run.objects.filter(pk=run.pk).update(status=Run.Status.COMPLETE, stage="complete", progress=1.,
                                             finished_at=timezone.now())
    except Cancelled:
        Run.objects.filter(pk=run.pk).update(stage="cancelled", finished_at=timezone.now())
    except Exception as error:  # record the failure on the run; the worker keeps going
        log.error("Run %s failed: %s", run.pk, traceback.format_exc())
        Run.objects.filter(pk=run.pk).update(status=Run.Status.FAILED, stage="failed",
                                             error=f"{type(error).__name__}: {error}"[:2000],
                                             finished_at=timezone.now())
    return Run.objects.get(pk=run.pk)


def recover_stale() -> int:
    """Runs left 'running' by a crashed worker are marked failed (re-submit to retry)."""
    return Run.objects.filter(status=Run.Status.RUNNING).update(
        status=Run.Status.FAILED, stage="failed", error="Worker stopped before the run finished; re-submit.",
        finished_at=timezone.now())


def work_forever(poll_s: float = 1., once: bool = False) -> None:
    while True:
        close_old_connections()
        run = claim_next()
        if run is None:
            if once:
                return
            time.sleep(poll_s)
            continue
        log.info("Processing run %s (%s, preset %s)", run.pk, run.video.name, run.preset)
        run_one(run)
        if once:
            return
