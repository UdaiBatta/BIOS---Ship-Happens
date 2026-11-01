"""Local readiness checks for a prepared MOTIONIQ run and benchmark restart."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import urllib.error
import urllib.request
import uuid

import psutil

from motioniq.ffmpeg import find_tool


API_ROOT = "http://127.0.0.1:8000/api"
MIN_FREE_BYTES = 2 * 1024**3
TIMEOUT_SECONDS = 4
LOCAL_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def request_json(path: str, token: str = "") -> dict:
    request = urllib.request.Request(f"{API_ROOT}/{path}")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    with LOCAL_OPENER.open(request, timeout=TIMEOUT_SECONDS) as response:
        return json.load(response)


def check_worker() -> tuple[bool, str]:
    backend_dir = Path(__file__).resolve().parent.parent / "backend"
    inaccessible_worker = False
    try:
        processes = psutil.process_iter(["cmdline"])
        for process in processes:
            try:
                args = process.info.get("cmdline") or []
            except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
                continue
            lowered = [str(arg).lower() for arg in args]
            if not (any(Path(arg).name.lower() == "manage.py" for arg in lowered)
                    and any("motioniq_worker" in arg for arg in lowered)):
                continue
            try:
                cwd = Path(process.cwd()).resolve()
                current_project = any(
                    (Path(arg) if Path(arg).is_absolute() else cwd / arg).resolve()
                    == (backend_dir / "manage.py").resolve()
                    for arg in args if Path(arg).name.lower() == "manage.py"
                )
            except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess, OSError):
                inaccessible_worker = True
                continue
            if current_project:
                return True, "worker process found"
    except (psutil.Error, OSError):
        return False, "process list unavailable"
    if inaccessible_worker:
        return False, "worker status could not be verified"
    return False, "worker process not found"


def check_power() -> tuple[bool, str]:
    try:
        battery = psutil.sensors_battery()
    except (OSError, psutil.Error, NotImplementedError):
        return False, "battery status unavailable"
    if battery is None:
        return True, "no battery detected"
    if battery.power_plugged:
        return True, "AC power connected"
    return False, "battery power detected; connect AC power"


def run_checks(run_id: str) -> list[tuple[str, bool, str]]:
    root = Path(__file__).resolve().parent.parent
    token = os.environ.get("MOTIONIQ_API_TOKEN", "")
    checks: list[tuple[str, bool, str]] = []

    for name in ("ffmpeg", "ffprobe"):
        found = find_tool(name) is not None
        checks.append((name, found, "available" if found else "not found (PATH or MOTIONIQ_FFMPEG_DIR)"))

    try:
        health = request_json("health", token)
        healthy = health.get("status") == "ok"
        checks.append(("local API", healthy, "healthy" if healthy else "health endpoint did not report ok"))
    except (OSError, urllib.error.URLError, TimeoutError, ValueError):
        checks.append(("local API", False, "127.0.0.1:8000 is not responding"))

    worker_ok, worker_note = check_worker()
    checks.append(("worker", worker_ok, worker_note))

    try:
        run_uuid = str(uuid.UUID(run_id))
        run_valid = True
    except (ValueError, AttributeError):
        run_valid = False
    if not run_valid:
        checks.append(("prepared run", False, "--run must be a run UUID"))
        checks.append(("prepared run frames", False, "run UUID is invalid"))
    else:
        try:
            run = request_json(f"runs/{run_uuid}", token)
            complete = run.get("status") == "complete"
            checks.append(("prepared run", complete, "complete" if complete else "run is not complete"))
        except (OSError, urllib.error.URLError, TimeoutError, ValueError):
            checks.append(("prepared run", False, "run could not be loaded from the local API"))
        try:
            page = request_json(f"runs/{run_uuid}/frames?max_frames=1", token)
            loaded = bool(page.get("frames")) and int(page.get("count", 0)) > 0
            checks.append(("prepared run frames", loaded, "frame API returned data" if loaded else "no frame data returned"))
        except (OSError, urllib.error.URLError, TimeoutError, ValueError, TypeError):
            checks.append(("prepared run frames", False, "frame API could not load data"))

    try:
        free = shutil.disk_usage(root).free
        enough = free >= MIN_FREE_BYTES
        gib = free / 1024**3
        checks.append(("disk space", enough, f"{gib:.1f} GiB free; 2 GiB minimum"))
    except OSError:
        checks.append(("disk space", False, "free space could not be checked"))

    power_ok, power_note = check_power()
    checks.append(("power", power_ok, power_note))
    return checks


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check local readiness for a prepared MOTIONIQ run.")
    parser.add_argument("--run", required=True, help="UUID of a completed run prepared for this benchmark")
    args = parser.parse_args(argv)

    checks = run_checks(args.run)
    for name, passed, detail in checks:
        status = "PASS" if passed else "FAIL"
        print(f"[{status}] {name}: {detail}")
    print("[NOTE] Power plan: select Best performance / High performance before timing.")
    return 0 if all(passed for _, passed, _ in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
