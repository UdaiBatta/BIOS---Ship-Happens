"""Find the same FFmpeg tools for the CLI, renderer and local backend."""
from __future__ import annotations

import os
from pathlib import Path
import shutil


def find_tool(name: str) -> str | None:
    if name not in {"ffmpeg", "ffprobe"}:
        raise ValueError("Expected ffmpeg or ffprobe")
    directory = os.environ.get("EGOHAND_FFMPEG_DIR")
    if directory:
        tool = shutil.which(name, path=str(Path(directory).expanduser()))
        if tool:
            return tool
    return shutil.which(name)


def require_tool(name: str) -> str:
    tool = find_tool(name)
    if tool is None:
        raise RuntimeError(f"{name} is required; install FFmpeg on PATH or set EGOHAND_FFMPEG_DIR to its bin folder")
    return tool
