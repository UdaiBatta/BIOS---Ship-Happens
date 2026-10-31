"""Parallel chunked detection: the latency path for multi-core machines.

Detection (MediaPipe inference) dominates processing time (about 52 of 64 s for 30 s of
1080p with the recall preset on a 4-vCPU VM). This module splits the processed frames
into contiguous chunks and runs detection for each chunk in its own process with its
own MediaPipe instance, then runs the normal pipeline once, in order, for tracking,
smoothing, exports and rendering, feeding it the precomputed detections.

Correctness rules:
- Every worker decodes its video SEQUENTIALLY from the first frame (grab() without
  conversion until its chunk), so frame index <-> PTS stays exact; no seeking.
- MediaPipe VIDEO mode carries tracking state between frames. Each chunk after the
  first starts ``overlap`` frames early and discards those warm-up results, so the state
  at the first kept frame resembles the sequential run. Results can still differ slightly
  near chunk boundaries; ``compare_runs`` measures that difference and it is reported.
- The tracker, smoothing and all exports run once over the full sequence, so track IDs
  and states are computed exactly as in sequential processing given the detections.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing
from pathlib import Path
import time

import cv2
import numpy as np


def _detect_chunk(job: dict) -> dict:
    """Worker: decode sequentially to the chunk, detect, return detections keyed by frame index."""
    from .pipeline import build_detector
    from .model import Detector
    args = argparse.Namespace(**job["args"])
    detector = build_detector(args)
    keep = set(job["keep"])
    lookahead = set(job.get("lookahead", []))
    process_frames = sorted(set(job["warmup"]) | keep | lookahead)
    wanted = set(process_frames)
    last = process_frames[-1]
    timestamps = job["timestamps"]
    results, latency, ahead = {}, [], {}
    cap = cv2.VideoCapture(job["video"])
    started = time.perf_counter()
    try:
        index = -1
        while index < last:
            if index + 1 in wanted:
                ok, frame = cap.read()
            else:
                ok, frame = cap.grab(), None
            if not ok:
                raise RuntimeError(f"video ended at frame {index} before {last}")
            index += 1
            if index not in wanted:
                continue
            h, w = frame.shape[:2]
            scale = min(1., args.max_width/w)
            resized = cv2.resize(frame, (round(w*scale), round(h*scale))) if scale < 1 else frame
            rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
            timestamp = timestamps[index] - timestamps[0]
            t0 = time.perf_counter()
            detections = (detector.detect(rgb, timestamp, frame) if not isinstance(detector, Detector)
                          else detector.detect(rgb, timestamp))
            if index in keep:
                latency.append(time.perf_counter() - t0)
                results[index] = detections
            elif index in lookahead:
                ahead[index] = detections
    finally:
        cap.release()
        detector.close()
    return {"chunk": job["chunk"], "detections": results, "lookahead": ahead, "latency": latency,
            "seconds": time.perf_counter() - started, "frames": len(keep), "warmup": len(job["warmup"])}


class PrecomputedDetector:
    """Feeds detections computed by the chunk workers to the sequential pipeline."""
    def __init__(self, by_timestamp: dict[float, list], latency: dict[float, float]):
        self.by_timestamp = by_timestamp
        self.latency = latency
        self.stats = None

    def detect(self, rgb, timestamp_s, full_bgr=None):
        key = round(timestamp_s, 6)
        if key not in self.by_timestamp:
            raise RuntimeError(f"no precomputed detections for t={timestamp_s:.6f}")
        return self.by_timestamp[key]

    def close(self):
        pass


def plan_chunks(frame_indices: list[int], workers: int, overlap: int, lookahead: int = 0) -> list[dict]:
    """Contiguous chunks; ``overlap`` warm-up frames before each chunk except the first and
    ``lookahead`` frames after each chunk except the last (used to repair the seam)."""
    chunks = [c for c in np.array_split(np.asarray(frame_indices), workers) if len(c)]
    plans = []
    position = 0
    for n, chunk in enumerate(chunks):
        keep = chunk.tolist()
        warmup = frame_indices[max(0, position - overlap):position] if n else []
        end = position + len(chunk)
        ahead = frame_indices[end:end + lookahead] if n < len(chunks) - 1 else []
        plans.append({"chunk": n, "keep": keep, "warmup": list(warmup), "lookahead": list(ahead)})
        position = end
    return plans


def same_detections(a: list, b: list) -> bool:
    if len(a) != len(b):
        return False
    return all(x.side == y.side and x.origin == y.origin and x.handedness_score == y.handedness_score
               and np.array_equal(x.image, y.image) and np.array_equal(x.world, y.world) for x, y in zip(a, b))


def merge_chunks(results: list[dict], agree: int = 5) -> tuple[dict, list[dict]]:
    """Stitch chunk results in order, repairing each seam.

    At a seam, the previous chunk's lookahead (sequential-like state) is used until it agrees
    exactly with the next chunk for ``agree`` consecutive frames; from there the next chunk's
    results are used. If they never agree within the lookahead, the previous chunk's lookahead
    is used for all of it and the seam is reported as unconverged.
    """
    results = sorted(results, key=lambda r: r["chunk"])
    merged = dict(results[0]["detections"])
    seams = []
    for prev, nxt in zip(results, results[1:]):
        ahead = prev["lookahead"]
        frames = sorted(ahead)
        switch = None
        for j in range(len(frames) - agree + 1):
            if all(same_detections(ahead[f], nxt["detections"][f]) for f in frames[j:j + agree]):
                switch = j
                break
        used_prev = frames if switch is None else frames[:switch]
        for f in used_prev:
            merged[f] = ahead[f]
        for f, detections in nxt["detections"].items():
            if f not in merged:
                merged[f] = detections
        seams.append({"after_chunk": prev["chunk"], "converged": switch is not None,
                      "frames_from_previous_chunk": len(used_prev), "lookahead_frames": len(frames)})
    return merged, seams


def process_parallel(args, progress=None, workers: int = 1, overlap: int = 15, lookahead: int = 60):
    """Process ``args`` with ``workers`` detection processes; workers=1 is the sequential pipeline."""
    from .pipeline import probe, process
    if workers <= 1:
        return process(args, progress=progress)
    started = time.perf_counter()
    timestamps = probe(Path(args.video), getattr(args, "timestamp_source", "auto"))["timestamps"]
    relative = np.asarray(timestamps) - timestamps[0]
    end = args.start_seconds + args.duration if args.duration is not None else np.inf
    selected = [i for i in np.flatnonzero((relative >= args.start_seconds) & (relative < end)).tolist()
                if i % args.stride == 0]
    if args.max_frames is not None:
        selected = selected[:args.max_frames]
    if not selected:
        raise ValueError("No frames in the selected interval")
    plain = {k: v for k, v in vars(args).items() if k != "func"}
    jobs = [{**plan, "args": plain, "video": str(args.video), "timestamps": list(timestamps)}
            for plan in plan_chunks(selected, workers, overlap, lookahead)]
    by_timestamp, latency, chunk_stats, results = {}, {}, [], []
    done = 0
    context = multiprocessing.get_context("spawn")  # MediaPipe is not fork-safe
    with ProcessPoolExecutor(max_workers=len(jobs), mp_context=context) as pool:
        for future in as_completed([pool.submit(_detect_chunk, job) for job in jobs]):
            result = future.result()
            results.append(result)
            for index, seconds in zip(sorted(result["detections"]), result["latency"]):
                latency[round(relative[index], 6)] = seconds
            chunk_stats.append({k: result[k] for k in ("chunk", "frames", "warmup", "seconds")})
            done += result["frames"]
            if progress is not None:
                progress(int(.8*done), len(selected))
    merged, seams = merge_chunks(results)
    for index, detections in merged.items():
        by_timestamp[round(relative[index], 6)] = detections
    detection_wall = time.perf_counter() - started
    detector = PrecomputedDetector(by_timestamp, latency)

    def tail_progress(processed, expected):
        if progress is not None:
            progress(int(.8*len(selected) + .2*processed*len(selected)/max(expected, 1)), len(selected))
    extra = {"parallel": {"workers": len(jobs), "overlap_frames": overlap, "lookahead_frames": lookahead,
                          "seams": seams, "seams_unconverged": sum(not s["converged"] for s in seams),
                          "detection_wall_seconds": round(detection_wall, 3),
                          "chunks": sorted(chunk_stats, key=lambda c: c["chunk"]),
                          "detector_cpu_seconds": round(sum(latency.values()), 3),
                          "note": ("Detection ran in parallel processes; the pipeline's 'detect' stage only "
                                   "looks up precomputed results. processing_seconds includes the parallel "
                                   "phase.")}}
    return process(args, progress=tail_progress, detector_override=detector, started=started,
                   extra_metrics=extra)


def compare_runs(a, b) -> dict:
    """Frame-by-frame difference of observed raw wrists between two runs of the same interval."""
    import json
    from pathlib import Path

    def load(run):
        return {json.loads(line)["frame_index"]: json.loads(line) for line in (Path(run)/"landmarks.jsonl").open()}
    ra, rb = load(a), load(b)
    if sorted(ra) != sorted(rb):
        raise ValueError("runs cover different frames")
    differ, max_shift = [], 0.
    for index in sorted(ra):
        wa = sorted(tuple(h["image_xyz_raw"][0][:2]) for h in ra[index]["hands"] if h["observed"])
        wb = sorted(tuple(h["image_xyz_raw"][0][:2]) for h in rb[index]["hands"] if h["observed"])
        if len(wa) != len(wb):
            differ.append(index)
            continue
        if wa:
            shift = float(np.max(np.abs(np.asarray(wa) - np.asarray(wb))))
            max_shift = max(max_shift, shift)
            if shift > 1e-6:
                differ.append(index)
    return {"frames": len(ra), "frames_differing": len(differ), "first_differing": differ[:20],
            "max_wrist_shift_normalized": max_shift}
