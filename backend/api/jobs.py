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
import os
from pathlib import Path
import socket
import time
import traceback

import psutil
from django.conf import settings
from django.db import close_old_connections
from django.utils import timezone

from .models import Run
from .services import assert_video_unchanged, build_frame_index, build_proxy, build_tracks, video_timestamps

log = logging.getLogger(__name__)


class Cancelled(Exception):
    pass


WORKER_ID = f"{socket.gethostname()}:{os.getpid()}"


def check_cancelled(run_id) -> None:
    if Run.objects.filter(pk=run_id, status=Run.Status.CANCELLED).exists():
        raise Cancelled()


def claim_next() -> Run | None:
    """Atomically move the oldest queued run to running; None if nothing is queued."""
    for run in Run.objects.filter(status=Run.Status.QUEUED).order_by("created_at")[:5]:
        claimed = Run.objects.filter(pk=run.pk, status=Run.Status.QUEUED).update(
            status=Run.Status.RUNNING, stage="starting", started_at=timezone.now(), progress=0., worker_id=WORKER_ID)
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
    if run.preset == "hybrid":
        argv += ["--rtm-models", str(settings.RTM_MODELS)]
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
    assert_video_unchanged(run.video)
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
    check_cancelled(run.pk)
    Run.objects.filter(pk=run.pk).update(stage="quality", progress=.9, metrics=metrics)
    summary = write_quality(out_dir, Path(run.video.path))
    Run.objects.filter(pk=run.pk).update(stage="indexing", progress=.97, quality_summary=summary)
    # Inputs for the viewer: whole-track side vote and the EXPERIMENTAL assumed-lens lift
    # (its summary carries "ASSUMED (not calibrated)", which the viewer displays).
    from egohand_twin.identity import write_identity
    write_identity(out_dir)
    from egohand_twin.motion_events import write_events
    write_events(out_dir)            # inferred candidate events (entry/exit/gap/hold/movement)
    if settings.LIFT_HFOV:
        from egohand_twin.lift import lift_run
        lift_run(out_dir, settings.LIFT_HFOV)
    check_cancelled(run.pk)
    index_path = build_frame_index(out_dir)
    build_tracks(out_dir)
    check_cancelled(run.pk)
    Run.objects.filter(pk=run.pk).update(stage="proxy", progress=.98)
    import numpy as np
    with np.load(index_path) as index:
        frame_indices = index["frame_index"]
        processed = len(frame_indices)
        if not processed or np.any(np.diff(frame_indices) != 1):
            raise RuntimeError("processed frames are not one contiguous source interval")
        first_frame, last_frame = int(frame_indices[0]), int(frame_indices[-1])
    assert_video_unchanged(run.video)
    timestamps = video_timestamps(run.video)
    proxy = build_proxy(Path(run.video.path), out_dir/"proxy.mp4", first_frame, last_frame,
                        float(timestamps[first_frame]))
    if proxy["frames"] != processed:
        # Never serve a proxy whose frames do not line up with the processed frames.
        (out_dir/"proxy.mp4").unlink(missing_ok=True)
        raise RuntimeError(f"proxy has {proxy['frames']} frames, run has {processed}")
    (out_dir/"proxy.json").write_text(__import__("json").dumps(proxy))


def run_one(run: Run, process=None) -> Run | None:
    """Execute one claimed run. Never raises: failures are recorded on the run.

    Final status updates are conditional on the run still being 'running', so a cancel that
    arrives during a late stage is never overwritten with 'complete' or 'failed'.
    """
    still_running = Run.objects.filter(pk=run.pk, status=Run.Status.RUNNING)
    try:
        execute(run, process)
        still_running.update(status=Run.Status.COMPLETE, stage="complete", progress=1., finished_at=timezone.now())
    except Cancelled:
        pass
    except Exception as error:  # record the failure on the run; the worker keeps going
        log.error("Run %s failed: %s", run.pk, traceback.format_exc())
        still_running.update(status=Run.Status.FAILED, stage="failed",
                             error=f"{type(error).__name__}: {error}"[:2000], finished_at=timezone.now())
    # Cancelled runs are finished once the worker has let go of them.
    Run.objects.filter(pk=run.pk, status=Run.Status.CANCELLED, finished_at__isnull=True).update(
        stage="cancelled", finished_at=timezone.now())
    return Run.objects.filter(pk=run.pk).first()


def _alive(worker_id: str) -> bool:
    host, _, pid = worker_id.rpartition(":")
    if host != socket.gethostname() or not pid.isdigit():
        return True  # another machine (or unknown): never steal its run
    return psutil.pid_exists(int(pid))


def recover_stale() -> int:
    """Release runs whose worker process on THIS host no longer exists.

    Running runs become 'failed' (re-submit to retry); cancelled runs the dead worker never
    released are marked finished. Runs held by live workers, or by workers on other hosts,
    are left alone, so starting a second worker with --recover cannot touch a live run.
    """
    now = timezone.now()
    dead = [r for r in Run.objects.filter(status__in=[Run.Status.RUNNING, Run.Status.CANCELLED],
                                          finished_at__isnull=True)
            if not r.worker_id or not _alive(r.worker_id)]
    failed = Run.objects.filter(pk__in=[r.pk for r in dead if r.status == Run.Status.RUNNING],
                                status=Run.Status.RUNNING, finished_at__isnull=True).update(
        status=Run.Status.FAILED, stage="failed", error="Worker stopped before the run finished; re-submit.",
        finished_at=now)
    Run.objects.filter(pk__in=[r.pk for r in dead],
                       status=Run.Status.CANCELLED, finished_at__isnull=True).update(
        stage="cancelled", finished_at=now)
    return failed


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
        try:
            run_one(run)
        except Exception:  # never let one run stop the worker loop
            log.error("Unexpected error around run %s: %s", run.pk, traceback.format_exc())
        if once:
            return
