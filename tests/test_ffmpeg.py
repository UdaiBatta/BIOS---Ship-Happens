from pathlib import Path

import pytest

from motioniq.ffmpeg import find_tool, require_tool


@pytest.fixture(autouse=True)
def clear_tool_cache():
    find_tool.cache_clear()
    yield
    find_tool.cache_clear()


def test_explicit_directory_takes_precedence_and_path_is_fallback(monkeypatch, tmp_path):
    monkeypatch.setenv("PATH", __import__("os").environ.get("PATH", ""))
    monkeypatch.setenv("MOTIONIQ_FFMPEG_DIR", str(tmp_path))
    calls = []

    def which(name, path=None):
        calls.append((name, path))
        return str(Path(path)/name) if path else "path-tool"

    monkeypatch.setattr("motioniq.tools.shutil.which", which)
    assert find_tool("ffprobe") == str(tmp_path/"ffprobe")
    assert calls == [("ffprobe", str(tmp_path))]
    monkeypatch.setattr("motioniq.tools.shutil.which", lambda name, path=None: None if path else "path-tool")
    assert find_tool("ffmpeg") == "path-tool"


def test_missing_tool_explains_how_to_fix_it(monkeypatch):
    monkeypatch.delenv("MOTIONIQ_FFMPEG_DIR", raising=False)
    monkeypatch.setattr("motioniq.tools.shutil.which", lambda *args, **kwargs: None)
    with pytest.raises(RuntimeError, match="MOTIONIQ_FFMPEG_DIR"):
        require_tool("ffprobe")
    with pytest.raises(ValueError):
        find_tool("other")
