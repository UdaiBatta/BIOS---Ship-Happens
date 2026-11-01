import json
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import urllib.error

import psutil

spec = importlib.util.spec_from_file_location("preflight", Path(__file__).parents[1] / "scripts" / "preflight.py")
preflight = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preflight)


class Response:
    def __init__(self, data):
        self.data = json.dumps(data).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.data


def test_api_request_keeps_token_in_header_and_uses_loopback(monkeypatch):
    seen = {}

    def urlopen(request, timeout):
        seen["url"] = request.full_url
        seen["auth"] = request.get_header("Authorization")
        seen["timeout"] = timeout
        return Response({"status": "ok"})

    monkeypatch.setattr(preflight.LOCAL_OPENER, "open", urlopen)
    assert preflight.request_json("health", "secret-value") == {"status": "ok"}
    assert seen["url"] == "http://127.0.0.1:8000/api/health"
    assert seen["auth"] == "Bearer secret-value"
    assert "secret-value" not in seen["url"]
    assert not any(isinstance(h, preflight.urllib.request.ProxyHandler)
                   for h in preflight.LOCAL_OPENER.handlers)


def test_worker_detection_matches_management_worker_without_printing_process_data(monkeypatch):
    backend = Path(preflight.__file__).resolve().parent.parent / "backend"
    worker = SimpleNamespace(info={"cmdline": ["python", "manage.py", "egohand_worker", "--recover"]},
                             cwd=lambda: str(backend))
    unrelated = SimpleNamespace(info={"cmdline": ["python", "manage.py", "egohand_worker"]},
                                cwd=lambda: str(backend.parent / "other-project"))
    monkeypatch.setattr(preflight.psutil, "process_iter", lambda attrs: [unrelated, worker])
    assert preflight.check_worker() == (True, "worker process found")


def test_worker_access_denied_is_a_failure(monkeypatch):
    class HiddenProcess:
        info = {"cmdline": ["python", "manage.py", "egohand_worker"]}

        def cwd(self):
            raise psutil.AccessDenied(pid=123)

    monkeypatch.setattr(preflight.psutil, "process_iter", lambda attrs: [HiddenProcess()])
    assert preflight.check_worker() == (False, "worker status could not be verified")


def test_power_check_requires_ac_when_a_battery_is_present(monkeypatch):
    monkeypatch.setattr(preflight.psutil, "sensors_battery", lambda: SimpleNamespace(power_plugged=False))
    assert preflight.check_power() == (False, "battery power detected; connect AC power")


def test_run_checks_report_each_required_check(monkeypatch):
    calls = []
    responses = [
        {"status": "ok"},
        {"status": "complete"},
        {"frames": [{"frame_index": 0}], "count": 1},
    ]

    def request_json(path, token):
        calls.append((path, token))
        return responses.pop(0)

    monkeypatch.setattr(preflight, "request_json", request_json)
    monkeypatch.setattr(preflight, "check_worker", lambda: (True, "worker process found"))
    monkeypatch.setattr(preflight, "check_power", lambda: (True, "AC power connected"))
    monkeypatch.setattr(preflight, "find_tool", lambda name: f"/{name}")
    monkeypatch.setattr(preflight.shutil, "disk_usage", lambda path: SimpleNamespace(free=3 * 1024**3))
    monkeypatch.setenv("EGOHAND_API_TOKEN", "never-print-me")

    checks = preflight.run_checks("12345678-1234-5678-1234-567812345678")

    assert [name for name, _, _ in checks] == [
        "ffmpeg", "ffprobe", "local API", "worker", "prepared run", "prepared run frames", "disk space", "power"
    ]
    assert all(passed for _, passed, _ in checks)
    assert calls == [
        ("health", "never-print-me"),
        ("runs/12345678-1234-5678-1234-567812345678", "never-print-me"),
        ("runs/12345678-1234-5678-1234-567812345678/frames?max_frames=1", "never-print-me"),
    ]


def test_invalid_run_id_fails_run_checks_without_requesting_it(monkeypatch):
    monkeypatch.setattr(preflight, "request_json", lambda path, token="": {"status": "ok"})
    monkeypatch.setattr(preflight, "check_worker", lambda: (True, "worker process found"))
    monkeypatch.setattr(preflight, "check_power", lambda: (True, "no battery detected"))
    monkeypatch.setattr(preflight, "find_tool", lambda name: name)
    monkeypatch.setattr(preflight.shutil, "disk_usage", lambda path: SimpleNamespace(free=3 * 1024**3))

    checks = preflight.run_checks("not-a-uuid")
    run_checks = [entry for entry in checks if entry[0].startswith("prepared run")]
    assert run_checks == [
        ("prepared run", False, "--run must be a run UUID"),
        ("prepared run frames", False, "run UUID is invalid"),
    ]


def test_cli_reports_failed_checks_and_returns_nonzero(monkeypatch, capsys):
    monkeypatch.setattr(preflight, "run_checks", lambda run_id: [("worker", False, "worker process not found")])
    assert preflight.main(["--run", "12345678-1234-5678-1234-567812345678"]) == 1
    output = capsys.readouterr().out
    assert output.count("[FAIL] worker:") == 1
    assert "Power plan:" in output


def test_cli_does_not_print_api_errors_or_token(monkeypatch, capsys):
    def failed_request(*args):
        raise urllib.error.URLError("token-secret C:\\private\\video.mp4")

    monkeypatch.setattr(preflight, "request_json", failed_request)
    monkeypatch.setattr(preflight, "check_worker", lambda: (True, "worker process found"))
    monkeypatch.setattr(preflight, "check_power", lambda: (True, "AC power connected"))
    monkeypatch.setattr(preflight, "find_tool", lambda name: name)
    monkeypatch.setattr(preflight.shutil, "disk_usage", lambda path: SimpleNamespace(free=3 * 1024**3))
    monkeypatch.setenv("EGOHAND_API_TOKEN", "token-secret")

    assert preflight.main(["--run", "12345678-1234-5678-1234-567812345678"]) == 1
    output = capsys.readouterr().out
    assert "token-secret" not in output
    assert "private\\video.mp4" not in output
