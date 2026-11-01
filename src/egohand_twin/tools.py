"""Find FFmpeg / FFprobe even when the current shell's PATH does not list them.

On Windows a fresh FFmpeg install (winget, Chocolatey, Scoop, a zip in C:\\ffmpeg) only reaches PATH in
shells opened AFTER the install, so a worker started from an older window failed with "FFprobe is
required". Lookup order:
1. ``EGOHAND_FFMPEG_DIR`` (a folder containing ffmpeg and ffprobe);
2. the current PATH;
3. Windows only: PATH as stored in the registry (machine + user), then the usual install folders.
A folder found outside PATH is also prepended to this process's PATH, so child processes find it too.
"""
from __future__ import annotations

from functools import lru_cache
import glob
import os
from pathlib import Path
import shutil
import sys


def _candidate_dirs() -> list[str]:
    dirs = []
    if os.environ.get("EGOHAND_FFMPEG_DIR"):
        dirs.append(os.environ["EGOHAND_FFMPEG_DIR"])
    if sys.platform != "win32":
        return dirs + ["/opt/homebrew/bin", "/usr/local/bin", "/usr/bin"]
    try:
        import winreg
        for root, key in ((winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
                          (winreg.HKEY_CURRENT_USER, "Environment")):
            try:
                with winreg.OpenKey(root, key) as handle:
                    value = winreg.QueryValueEx(handle, "Path")[0]
                dirs += [os.path.expandvars(d) for d in value.split(";") if d]
            except OSError:
                pass
    except ImportError:
        pass
    local = os.environ.get("LOCALAPPDATA", "")
    if local:
        dirs.append(os.path.join(local, "Microsoft", "WinGet", "Links"))
        dirs += sorted(glob.glob(os.path.join(local, "Microsoft", "WinGet", "Packages", "*FFmpeg*", "**", "bin"),
                                 recursive=True), reverse=True)
    for base in (os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("ProgramFiles(x86)", ""), "C:\\"):
        if base:
            dirs += [os.path.join(base, "ffmpeg", "bin")]
            dirs += sorted(glob.glob(os.path.join(base, "ffmpeg*", "bin")), reverse=True)
    dirs += [os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"), "chocolatey", "bin"),
             os.path.join(os.path.expanduser("~"), "scoop", "shims")]
    return dirs


@lru_cache(maxsize=None)
def tool(name: str) -> str | None:
    """Full path of ``name`` (``ffmpeg`` or ``ffprobe``), or None when it is not installed anywhere known."""
    found = shutil.which(name)
    if found:
        return found
    for folder in _candidate_dirs():
        found = shutil.which(name, path=folder)
        if found:
            parent = str(Path(found).parent)
            if parent not in os.environ.get("PATH", "").split(os.pathsep):
                os.environ["PATH"] = parent + os.pathsep + os.environ.get("PATH", "")
            return found
    return None


def require(name: str) -> str:
    path = tool(name)
    if not path:
        raise RuntimeError(
            f"{name} was not found. Install FFmpeg (Windows: winget install --id=Gyan.FFmpeg -e) and start the worker "
            f"from a NEW terminal, or set EGOHAND_FFMPEG_DIR to the folder that contains {name}.")
    return path
