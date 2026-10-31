"""Entry point for processing with optional parallelism (see process_parallel)."""
from __future__ import annotations

from .pipeline import process


def process_parallel(args, progress=None, workers: int = 1):
    """Process ``args`` with ``workers`` CPU processes. workers=1 is the sequential pipeline."""
    if workers <= 1:
        return process(args, progress=progress)
    raise NotImplementedError("parallel chunked detection is not available yet; use workers=1")
