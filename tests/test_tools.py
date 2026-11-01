"""FFmpeg / FFprobe are found even when the shell's PATH does not list them (Windows shells opened before the install)."""
import os
import shutil
import stat

import pytest

from egohand_twin import tools


@pytest.fixture(autouse=True)
def fresh_cache():
    tools.tool.cache_clear()
    yield
    tools.tool.cache_clear()


def _fake(folder, name):
    exe = folder/(name + (".exe" if os.name == "nt" else ""))
    exe.write_text("#!/bin/sh\n")
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    return exe


def test_found_through_egohand_ffmpeg_dir_when_not_on_path(tmp_path, monkeypatch):
    _fake(tmp_path, "ffprobe")
    monkeypatch.setenv("PATH", str(tmp_path/"empty"))
    monkeypatch.setenv("EGOHAND_FFMPEG_DIR", str(tmp_path))
    found = tools.tool("ffprobe")
    assert found and os.path.dirname(found) == str(tmp_path)
    assert os.environ["PATH"].split(os.pathsep)[0] == str(tmp_path)   # child processes find it too
    assert shutil.which("ffprobe") == found


def test_missing_tool_gives_an_actionable_error(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.delenv("EGOHAND_FFMPEG_DIR", raising=False)
    monkeypatch.setattr(tools, "_candidate_dirs", lambda: [str(tmp_path)])
    assert tools.tool("ffprobe") is None
    with pytest.raises(RuntimeError, match="NEW terminal.*EGOHAND_FFMPEG_DIR"):
        tools.require("ffprobe")
