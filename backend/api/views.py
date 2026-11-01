"""JSON API for the MOTIONIQ frontend. See docs/BACKEND_API.md for the contract."""
from __future__ import annotations

from functools import wraps
import json
import math
import mimetypes
import os
from pathlib import Path
import re
import shutil
import subprocess
import uuid

from django.conf import settings
from django.http import FileResponse, HttpResponse, JsonResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt

from motioniq.model import sha256
from motioniq.pipeline import probe

from . import services
from .models import ReviewDecision, Run, Video

API_VERSION = "1"
PRESETS = {
    "baseline": {"description": "MediaPipe defaults (historical B0); fastest",
                 "measured": "holdout recall 19/78, precision 19/19 (provisional labels, one clip)"},
    "recall": {"description": "Thresholds 0.3 + centre-crop rescue; about 2x detector time",
               "measured": "holdout recall 39/78, precision 39/40 (provisional labels, one clip); "
                           "more track fragmentation"},
    "accurate": {"description": "recall + a reverse-time detection pass; about 2x detector time",
                 "measured": "holdout recall 46/78, precision 46/48 (provisional labels, one clip); "
                             "dev 41/72 with no false positives"},
    "hybrid": {"description": "EXPERIMENTAL: recall + an RTMDet hand detector for hands MediaPipe misses; "
                              "RTMPose 2D with fitted depth where MediaPipe still fails; about 3x slower",
               "measured": "dev: no recall gain (36/72) and 11 false positives (precision 0.77), provisional "
                           "labels, one clip; try it on other recording families only"},
}


def available_presets() -> dict:
    """Presets this installation can run (hybrid needs onnxruntime and the RTM hand models)."""
    names = dict(PRESETS)
    try:
        import onnxruntime  # noqa: F401
        ready = all((settings.RTM_MODELS/n).exists() for n in ("rtmdet_nano_hand.onnx", "rtmpose_m_hand.onnx"))
    except ImportError:
        ready = False
    if not ready:
        names.pop("hybrid")
    return names


class ApiError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def api(methods: tuple[str, ...]):
    """JSON endpoint decorator: method check, JSON errors, CSRF-exempt (token auth instead)."""
    def decorator(view):
        @csrf_exempt
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if request.method not in methods:
                return JsonResponse({"error": f"method {request.method} not allowed"}, status=405)
            try:
                result = view(request, *args, **kwargs)
            except ApiError as error:
                return JsonResponse({"error": str(error)}, status=error.status)
            except services.NotReady as error:
                return JsonResponse({"error": f"not ready: {error}"}, status=409)
            except services.SourceChanged as error:
                return JsonResponse({"error": str(error)}, status=409)
            except (Video.DoesNotExist, Run.DoesNotExist, FileNotFoundError) as error:
                return JsonResponse({"error": f"not found: {error}"}, status=404)
            except PermissionError as error:
                return JsonResponse({"error": str(error)}, status=403)
            if isinstance(result, (HttpResponse, StreamingHttpResponse)):
                return result
            return JsonResponse(result, safe=False, json_dumps_params={"separators": (",", ":")})
        return wrapper
    return decorator


def body(request) -> dict:
    if request.content_type != "application/json":
        raise ApiError("Content-Type must be application/json", 415)
    try:
        data = json.loads(request.body or b"{}")
    except (ValueError, UnicodeDecodeError):
        raise ApiError("request body must be JSON")
    if not isinstance(data, dict):
        raise ApiError("request body must be a JSON object")
    return data


def number(request, name, default=None, cast=float):
    value = request.GET.get(name)
    if value in (None, ""):
        return default
    try:
        return cast(value)
    except ValueError:
        raise ApiError(f"{name} must be a number")


def run_dir(run: Run, require_complete: bool = True) -> Path:
    if require_complete and run.status != Run.Status.COMPLETE:
        raise services.NotReady(f"run is {run.status}")
    if not run.out_dir:
        raise services.NotReady("run has no output yet")
    return Path(run.out_dir)


# --------------------------------------------------------------------------- meta
@api(("GET",))
def health(request):
    return {"status": "ok", "api_version": API_VERSION, "model_present": settings.MODEL_PATH.exists(),
            "auth_required": bool(settings.API_TOKEN),
            "queue": {s: Run.objects.filter(status=s).count() for s in ("queued", "running")}}


@api(("GET",))
def presets(request):
    return {"presets": available_presets(), "default": "recall",
            "note": "Measurements are provisional (labels not yet human-reviewed) and from one clip."}


# --------------------------------------------------------------------------- videos
def register_video(path: Path) -> Video:
    source_sha = sha256(path)
    existing = Video.objects.filter(path=str(path)).first()
    if existing:
        if existing.sha256 != source_sha:
            raise ApiError("registered source video changed; restore it or register the replacement at a new path", 409)
        return existing
    info = probe(path)
    frames = len(info["timestamps"])
    return Video.objects.create(
        name=services.display_name(path), path=str(path), sha256=source_sha, width=int(info["width"]), height=int(info["height"]),
        fps=info["fps"], frame_count=frames, duration_s=float(info["timestamps"][-1] - info["timestamps"][0]),
        timestamp_source=info["timestamp_source"])


VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".avi", ".m4v", ".webm"}


def scan_media(paths=None) -> dict:
    """Register every video under the allowed media folders (or the given files/folders).

    Already registered files are skipped without re-hashing (processing verifies the hash before a
    run is queued and again in the worker), so a rescan only costs time for NEW files. Unreadable
    files are reported, never fatal.
    """
    targets = [Path(p) for p in paths] if paths else [r for r in settings.MEDIA_ROOTS if r.is_dir()]
    files = []
    for target in targets:
        if target.is_dir():
            files += sorted(p for p in target.rglob("*") if p.is_file() and p.suffix.lower() in VIDEO_SUFFIXES)
        else:
            files.append(target)
    report = {"registered": [], "already_registered": 0, "failed": []}
    for path in files:
        try:
            resolved = services.allowed_media_path(path)
            if Video.objects.filter(path=str(resolved)).exists():
                report["already_registered"] += 1
                continue
            report["registered"].append(register_video(resolved).as_dict())
        except subprocess.CalledProcessError:
            report["failed"].append({"name": path.name, "error": "not a readable video (FFprobe could not open it)"})
        except Exception as error:  # outside the allowed folders, changed or corrupt
            report["failed"].append({"name": path.name, "error": str(error)[:300]})
    return report


@api(("POST",))
def videos_scan(request):
    """Find videos added to the media folders since the server started."""
    return scan_media()


@api(("GET", "POST"))
def videos(request):
    if request.method == "GET":
        return {"videos": [v.as_dict() for v in Video.objects.order_by("-created_at")]}
    path = body(request).get("path")
    if not path:
        raise ApiError("path is required (a file under MOTIONIQ_MEDIA_ROOTS)")
    return JsonResponse(register_video(services.allowed_media_path(path)).as_dict(), status=201)


@api(("POST",))
def upload_video(request):
    upload = request.FILES.get("file")
    if upload is None:
        raise ApiError("multipart field 'file' is required")
    suffix = Path(upload.name).suffix.lower()
    if suffix not in {".mp4", ".mov", ".mkv", ".avi"}:
        raise ApiError("unsupported file type")
    settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    target = settings.UPLOAD_DIR/f"{uuid.uuid4().hex}{suffix}"
    with target.open("wb") as f:
        for chunk in upload.chunks():
            f.write(chunk)
    try:
        video = register_video(services.allowed_media_path(target))
    except ApiError:
        target.unlink(missing_ok=True)
        raise
    except Exception:
        target.unlink(missing_ok=True)
        raise ApiError("uploaded file could not be read as a video")
    return JsonResponse(video.as_dict(), status=201)


@api(("GET",))
def video_detail(request, video_id: int):
    video = Video.objects.get(pk=video_id)
    return {**video.as_dict(), "runs": [r.as_dict() for r in video.runs.all()]}


@api(("GET",))
def video_frame(request, video_id: int, frame_index: int):
    video = Video.objects.get(pk=video_id)
    services.assert_video_unchanged(video)
    if not 0 <= frame_index < video.frame_count:
        raise ApiError("frame_index out of range", 404)
    width = number(request, "width", min(640, video.width), int)
    if not 64 <= width <= video.width:
        raise ApiError(f"width must be between 64 and {video.width}")
    timestamps = services.video_timestamps(video)  # probed once, cached
    jpeg = services.frame_jpeg(Path(video.path), video.sha256, frame_index, float(timestamps[frame_index]), width)
    response = FileResponse(jpeg.open("rb"), content_type="image/jpeg")
    response["Cache-Control"] = "private, max-age=86400, immutable"
    return response


@api(("GET",))
def video_frame_at(request, video_id: int):
    video = Video.objects.get(pk=video_id)
    services.assert_video_unchanged(video)
    time_s = number(request, "time_s")
    if time_s is None or not math.isfinite(time_s) or time_s < 0:
        raise ApiError("time_s must be a finite, non-negative number")
    timestamps = services.video_timestamps(video)
    if time_s > timestamps[-1]:
        raise ApiError("time_s outside the video")
    frame_index = int(timestamps.searchsorted(time_s, side="left"))
    return {"frame_index": frame_index, "timestamp_s": float(timestamps[frame_index])}


# --------------------------------------------------------------------------- runs
@api(("GET", "POST"))
def runs(request):
    if request.method == "GET":
        qs = Run.objects.select_related("video").all()
        video_id = number(request, "video_id", cast=int)
        if video_id is not None:
            qs = qs.filter(video_id=video_id)
        if request.GET.get("status"):
            qs = qs.filter(status=request.GET["status"])
        return {"runs": [r.as_dict() for r in qs[:200]]}
    data = body(request)

    def field(name, cast, default=None):
        value = data.get(name, default)
        if value is None:
            return None
        if isinstance(value, bool):
            raise ApiError(f"{name} must be a number")
        try:
            return cast(value)
        except (TypeError, ValueError):
            raise ApiError(f"{name} must be a number")
    video_id = field("video_id", int)
    if video_id is None:
        raise ApiError("video_id is required")
    preset = data.get("preset", "recall")
    if preset not in available_presets():  # cheap checks first: no video hashing for a bad request
        raise ApiError(f"preset must be one of {sorted(available_presets())}"
                       + (" (hybrid needs: uv sync --extra hybrid; motioniq fetch-model --rtm)" if preset == "hybrid" else ""))
    video = Video.objects.get(pk=video_id)
    services.assert_video_unchanged(video)
    start = field("start_s", float, 0.)
    duration = field("duration_s", float)
    timestamps = services.video_timestamps(video)
    if not math.isfinite(start) or start < 0 or start > timestamps[-1]:
        raise ApiError("start_s outside the video")
    if duration is not None and (not math.isfinite(duration) or duration <= 0):
        raise ApiError("duration_s must be positive")
    if duration is not None and timestamps.searchsorted(start + duration, side="left") == timestamps.searchsorted(start, side="left"):
        raise ApiError("requested interval contains no video frames")
    # 2 detection processes measured identical to sequential and ~20% faster on a 4-vCPU host.
    workers = field("workers", int, 2 if (os.cpu_count() or 1) >= 4 else 1)
    if not 1 <= workers <= (os.cpu_count() or 1):
        raise ApiError(f"workers must be between 1 and {os.cpu_count()}")
    run = Run.objects.create(video=video, preset=preset, start_s=start, duration_s=duration, workers=workers,
                             render_preview=bool(data.get("render_preview", False)),
                             write_rrd=bool(data.get("write_rrd", False)))
    return JsonResponse(run.as_dict(), status=202)


@api(("GET", "DELETE"))
def run_detail(request, run_id):
    run = Run.objects.select_related("video").get(pk=run_id)
    if request.method == "DELETE":
        if run.status in (Run.Status.QUEUED, Run.Status.RUNNING) or run.finished_at is None:
            raise ApiError("the run is queued, running or still stopping; cancel it and wait until it has finished", 409)
        if run.out_dir:
            output = Path(run.out_dir)
            if output.resolve() != (settings.RUNS_DIR/str(run.id)).resolve() or output.is_symlink():
                raise ApiError("run output is outside its backend directory", 409)
            try:
                shutil.rmtree(output)
            except FileNotFoundError:
                if output.exists():
                    raise ApiError("could not remove run output; retry deletion", 503)
            except OSError as error:
                raise ApiError(f"could not remove run output; retry deletion: {error}", 503)
        run.delete()
        return HttpResponse(status=204)
    data = run.as_dict(detail=True)
    data["video"] = run.video.as_dict()
    if run.status == Run.Status.COMPLETE:
        directory = run_dir(run)
        proxy_path = directory/"proxy.json"
        proxy = services.cached_json(proxy_path) if proxy_path.exists() else None
        data["proxy"] = proxy if proxy and services.frame_exact_proxy(proxy) else None
        identity = directory/"identity.json"
        lifts = sorted(path for path in directory.glob("lift_hfov*.json")
                       if re.fullmatch(r"lift_hfov\d{2,3}\.json", path.name)
                       and path.with_suffix(".npz").is_file())
        lift = lifts[0] if lifts else None
        data["artifacts"] = {
            "identity": identity.name if identity.is_file() else None,
            "motion_events": "motion_events.json" if (directory/"motion_events.json").is_file() else None,
            "lift": {"summary": lift.name, "arrays": lift.with_suffix(".npz").name} if lift else None,
        }
    else:
        data.update(proxy=None, artifacts={"identity": None, "lift": None, "motion_events": None})
    return data


@api(("POST",))
def run_cancel(request, run_id):
    from django.utils import timezone
    queued = Run.objects.filter(pk=run_id, status=Run.Status.QUEUED).update(
        status=Run.Status.CANCELLED, stage="cancelled", finished_at=timezone.now())
    # A running run is released (finished_at set) by its worker at the next cancellation check.
    running = Run.objects.filter(pk=run_id, status=Run.Status.RUNNING).update(status=Run.Status.CANCELLED)
    if not queued and not running:
        raise ApiError("run is not queued or running", 409)
    return Run.objects.get(pk=run_id).as_dict()


@api(("GET",))
def run_manifest(request, run_id):
    return services.cached_json(run_dir(Run.objects.get(pk=run_id))/"manifest.json")


@api(("GET",))
def run_frames(request, run_id):
    directory = run_dir(Run.objects.get(pk=run_id))
    detail = request.GET.get("detail", "lite")
    if detail not in ("lite", "full"):
        raise ApiError("detail must be lite or full")
    limit = min(number(request, "max_frames", settings.MAX_FRAMES_PER_REQUEST, int), settings.MAX_FRAMES_PER_REQUEST)
    if limit < 1:
        raise ApiError("max_frames must be positive")
    return services.read_frames(directory, number(request, "start_s"), number(request, "end_s"), limit, detail)


@api(("GET",))
def run_frame(request, run_id, frame_index: int):
    detail = request.GET.get("detail", "full")
    try:
        return services.read_frame(run_dir(Run.objects.get(pk=run_id)), frame_index, detail)
    except KeyError:
        raise ApiError(f"frame {frame_index} was not processed in this run", 404)


@api(("GET",))
def run_tracks(request, run_id):
    return services.tracks(run_dir(Run.objects.get(pk=run_id)))


@api(("GET",))
def run_events(request, run_id):
    directory = run_dir(Run.objects.get(pk=run_id))
    return {"events": services.events(directory, number(request, "start_s"), number(request, "end_s"))}


@api(("GET",))
def run_quality(request, run_id):
    directory = run_dir(Run.objects.get(pk=run_id))/"quality"
    data = {"summary": services.cached_json(directory/"quality_summary.json")}
    if request.GET.get("windows", "1") != "0":
        data["windows"] = services.cached_json(directory/"quality_windows.json")
    return data


@api(("GET",))
def run_review_queue(request, run_id):
    run = Run.objects.get(pk=run_id)
    queue = services.cached_json(run_dir(run)/"quality"/"review_queue.json")
    status = request.GET.get("status")
    decisions: dict[str, list] = {}
    for d in run.decisions.all():
        decisions.setdefault(d.item_id, []).append(d.as_dict())
    items = [{**q, "decisions": decisions.get(q["item_id"], [])} for q in queue
             if status is None or q["status"] == status]
    items.sort(key=lambda q: (q["status"] != "needs_review", -q["priority_score"], q["start_s"]))
    return {"items": items, "count": len(items)}


@api(("POST",))
def review_decision(request, run_id, item_id: str):
    run = Run.objects.get(pk=run_id)
    queue = services.cached_json(run_dir(run)/"quality"/"review_queue.json")
    events_path = run_dir(run)/"motion_events.json"
    motion_ids = {e["event_id"] for e in services.cached_json(events_path)["events"]} if events_path.exists() else set()
    # Review-queue items and candidate motion events share the decision store (confirm = confirmed_issue,
    # reject = false_alarm for a motion event).
    if item_id not in {q["item_id"] for q in queue} | motion_ids:
        raise ApiError("unknown review item", 404)
    data = body(request)
    verdict, reviewer = data.get("verdict"), (data.get("reviewer") or "").strip()
    if verdict not in ReviewDecision.Verdict.values:
        raise ApiError(f"verdict must be one of {ReviewDecision.Verdict.values}")
    if not reviewer or len(reviewer) > 64:
        raise ApiError("reviewer (initials) is required")
    decision = ReviewDecision.objects.create(run=run, item_id=item_id, verdict=verdict, reviewer=reviewer,
                                             note=str(data.get("note", ""))[:2000])
    return JsonResponse(decision.as_dict(), status=201)


@api(("GET",))
def run_decisions(request, run_id):
    """All review decisions of a run (quality-queue items and candidate motion events), oldest first."""
    run = Run.objects.get(pk=run_id)
    return {"decisions": [{**d.as_dict(), "item_id": d.item_id} for d in run.decisions.all()]}


@api(("GET",))
def review_stats(request, run_id):
    """Measured usefulness of the quality flags from human decisions (latest per item)."""
    run = Run.objects.get(pk=run_id)
    queue = {q["item_id"]: q for q in services.cached_json(run_dir(run)/"quality"/"review_queue.json")}
    latest = {}
    for d in run.decisions.all():
        latest[d.item_id] = d
    flagged = [i for i, q in queue.items() if q["status"] == "needs_review"]
    reviewed = [i for i in flagged if i in latest]
    confirmed = sum(latest[i].verdict == "confirmed_issue" for i in reviewed)
    false_alarm = sum(latest[i].verdict == "false_alarm" for i in reviewed)
    by_reason: dict[str, dict] = {}
    for i in reviewed:
        for reason in queue[i]["reason_window_counts"]:
            entry = by_reason.setdefault(reason, {"confirmed_issue": 0, "false_alarm": 0})
            if latest[i].verdict in entry:
                entry[latest[i].verdict] += 1
    return {"flagged_items": len(flagged), "reviewed_items": len(reviewed),
            "confirmed_issue": confirmed, "false_alarm": false_alarm,
            "flag_precision": confirmed/(confirmed+false_alarm) if confirmed+false_alarm else None,
            "by_reason": by_reason,
            "note": "Precision of needs_review flags as judged by reviewers; items without a decision are excluded."}


RANGE = re.compile(r"bytes=(\d*)-(\d*)$")


def ranged_file(path: Path, request, content_type: str):
    """Serve a file with HTTP Range support so the browser can seek without downloading it all."""
    size = path.stat().st_size
    match = RANGE.match(request.headers.get("Range", ""))
    if not match:
        response = FileResponse(path.open("rb"), content_type=content_type)
        response["Accept-Ranges"] = "bytes"
        return response
    first, last = match.groups()
    if first == "" and last == "":
        response = HttpResponse(status=416)
        response["Content-Range"] = f"bytes */{size}"
        return response
    if first == "":
        start, end = max(0, size - int(last)), size - 1
    else:
        start, end = int(first), min(int(last) if last else size - 1, size - 1)
    if start > end or start >= size:
        response = HttpResponse(status=416)
        response["Content-Range"] = f"bytes */{size}"
        return response

    def stream(chunk=1 << 16):
        with path.open("rb") as f:
            f.seek(start)
            remaining = end - start + 1
            while remaining > 0:
                data = f.read(min(chunk, remaining))
                if not data:
                    break
                remaining -= len(data)
                yield data
    response = StreamingHttpResponse(stream(), status=206, content_type=content_type)
    response["Content-Range"] = f"bytes {start}-{end}/{size}"
    response["Content-Length"] = str(end - start + 1)
    response["Accept-Ranges"] = "bytes"
    return response


@api(("GET",))
def run_preview(request, run_id):
    path = run_dir(Run.objects.get(pk=run_id))/"preview.mp4"
    if not path.exists():
        raise services.NotReady("preview.mp4 (submit the run with render_preview=true)")
    return ranged_file(path, request, "video/mp4")


@api(("GET",))
def run_proxy(request, run_id):
    """Frame-exact H.264 run proxy; old proxies need regeneration before serving."""
    directory = run_dir(Run.objects.get(pk=run_id))
    path = directory/"proxy.mp4"
    if not path.exists():
        raise services.NotReady("proxy.mp4")
    metadata_path = directory/"proxy.json"
    if not metadata_path.exists() or not services.frame_exact_proxy(services.cached_json(metadata_path)):
        raise ApiError("proxy predates frame-exact alignment; submit a new run", 409)
    response = ranged_file(path, request, "video/mp4")
    response["Cache-Control"] = "private, max-age=86400"
    return response


@api(("GET",))
def run_artifact(request, run_id, name: str):
    """Download whitelisted run files (exports) for analysis."""
    allowed = {"landmarks.jsonl", "landmarks.csv", "landmarks.npz", "manifest.json", "metrics.json",
               "tracking_events.csv", "replay.rrd", "quality/review_queue.csv", "quality/quality_frames.csv",
               "identity.json", "motion_events.json"}
    if re.fullmatch(r"lift_hfov\d{2,3}\.(npz|json)", name):
        allowed.add(name)
    if name not in allowed:
        raise ApiError(f"artifact must be one of {sorted(allowed)}", 404)
    path = run_dir(Run.objects.get(pk=run_id))/name
    if not path.exists():
        raise services.NotReady(name)
    response = FileResponse(path.open("rb"), as_attachment=True, filename=path.name,
                            content_type=mimetypes.guess_type(path.name)[0] or "application/octet-stream")
    return response


@api(("GET",))
def run_compare(request, run_id):
    """Same-moment flat-vs-3D image at ?t= seconds (cached per frame)."""
    from motioniq.compare import compare, find_frame
    run = Run.objects.select_related("video").get(pk=run_id)
    directory = run_dir(run)
    t = number(request, "t")
    if t is None:
        raise ApiError("t (seconds on the run time base) is required")
    try:
        record = find_frame(directory, time_s=t)
    except ValueError as error:
        raise ApiError(str(error), 404)
    png = directory/"compare"/f"frame_{record['frame_index']:06d}.png"
    out = png.with_suffix(".jpg")
    if not out.exists():
        if not png.exists():
            services.assert_video_unchanged(run.video)
            compare(Path(run.video.path), directory, png, frame_index=record["frame_index"])
        import cv2
        cv2.imwrite(str(out), cv2.imread(str(png)), [cv2.IMWRITE_JPEG_QUALITY, 88])  # ~10x smaller than PNG
    response = FileResponse(out.open("rb"), content_type="image/jpeg")
    response["Cache-Control"] = "private, max-age=86400"
    return response


# --------------------------------------------------------------------------- viewer
FRONTEND_FILES = {"": ("index.html", "text/html; charset=utf-8"),
                  "backend-connector.js": ("backend-connector.js", "text/javascript; charset=utf-8"),
                  "hand-mesh.js": ("hand-mesh.js", "text/javascript; charset=utf-8")}


def frontend(request, name: str = ""):
    """Serve the teammate's viewer prototype (same origin as the API, so no CORS is needed)."""
    if name not in FRONTEND_FILES:
        return JsonResponse({"error": "not found"}, status=404)
    filename, content_type = FRONTEND_FILES[name]
    path = settings.FRONTEND_DIR/filename
    if not path.exists():
        return JsonResponse({"error": f"{filename} not found in MOTIONIQ_FRONTEND_DIR"}, status=404)
    response = HttpResponse(path.read_bytes(), content_type=content_type)
    response["Cache-Control"] = "no-store"   # a git pull must always reach the browser on the next reload
    return response
