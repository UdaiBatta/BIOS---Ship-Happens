"""Benchmark presets on the SAME clip and interval on this machine (run it on the team laptop).

Usage:  uv run python scripts/benchmark_hybrid.py VIDEO --duration 30 [--start 0] [--workers 2]
            [--presets baseline recall accurate hybrid] [--out runs/bench]

For each preset it runs `egohand process --no-video` into a fresh folder and reports wall
seconds, end-to-end FPS, detector p50/p95 per frame, per-stage seconds and the sampled peak
RSS from metrics.json. MediaPipe runs on the CPU (its Python GPU delegate is not available on
Windows); the RTM models run with onnxruntime on the CPU. Outputs stay under runs/ (git-ignored).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import platform
import subprocess
import sys
import time


def main():
    p = argparse.ArgumentParser()
    p.add_argument("video")
    p.add_argument("--start", type=float, default=0.)
    p.add_argument("--duration", type=float, default=30.)
    p.add_argument("--workers", type=int, default=2)
    p.add_argument("--presets", nargs="+", default=["baseline", "recall", "accurate", "hybrid"])
    p.add_argument("--out", default="runs/bench")
    a = p.parse_args()
    stamp = time.strftime("%Y%m%d-%H%M%S")
    rows = []
    for preset in a.presets:
        out = Path(a.out)/f"{stamp}-{preset}"
        cmd = [sys.executable, "-m", "egohand_twin.cli", "process", a.video, "--out", str(out), "--preset", preset,
               "--start-seconds", str(a.start), "--duration", str(a.duration), "--workers", str(a.workers), "--no-video"]
        t0 = time.perf_counter()
        done = subprocess.run(cmd, capture_output=True, text=True)
        wall = time.perf_counter() - t0
        out.mkdir(parents=True, exist_ok=True)
        (out/"stdout.log").write_text(done.stdout, encoding="utf-8", errors="replace")
        (out/"stderr.log").write_text(done.stderr, encoding="utf-8", errors="replace")
        if done.returncode:
            rows.append({"preset": preset, "error": done.stderr.strip().splitlines()[-1:],
                         "exit_code": done.returncode, "run": str(out)})
            continue
        m = json.loads((out/"metrics.json").read_text())
        rows.append({"preset": preset, "wall_s": round(wall, 1), "processing_seconds": m["processing_seconds"],
                     "end_to_end_fps": m["end_to_end_fps"],
                     "detector_p50_ms": m.get("inference_p50_ms"), "detector_p95_ms": m.get("inference_p95_ms"),
                     "peak_rss_mb": m.get("sampled_peak_process_rss_mb"), "stage_seconds": m["stage_seconds"],
                     "frames": m["processed_frames"], "detector_stats": m.get("detector_stats"), "run": str(out)})
    print(json.dumps({"machine": {"platform": platform.platform(), "processor": platform.processor(),
                                  "python": platform.python_version()},
                      "interval": [a.start, a.start + a.duration], "workers": a.workers, "results": rows}, indent=2))


    return 1 if any("error" in row for row in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
