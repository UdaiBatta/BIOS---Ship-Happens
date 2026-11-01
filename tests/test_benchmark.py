import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace


spec = importlib.util.spec_from_file_location("benchmark_hybrid", Path(__file__).parents[1]/"scripts"/"benchmark_hybrid.py")
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


def test_failed_preset_fails_benchmark_and_preserves_diagnostics(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(benchmark.sys, "argv", ["benchmark_hybrid.py", "input.mp4", "--presets", "accurate", "--out", str(tmp_path)])
    monkeypatch.setattr(benchmark.subprocess, "run", lambda *args, **kwargs:
                        SimpleNamespace(returncode=5, stdout="partial output", stderr="full diagnostic\nlast line"))
    assert benchmark.main() == 1
    report = json.loads(capsys.readouterr().out)
    assert report["results"][0]["exit_code"] == 5
    run = Path(report["results"][0]["run"])
    assert (run/"stderr.log").read_text() == "full diagnostic\nlast line"
    assert (run/"stdout.log").read_text() == "partial output"
