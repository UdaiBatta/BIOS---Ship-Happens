"""JSON API for the EgoHand Twin frontend. See docs/BACKEND_API.md for the contract."""
from __future__ import annotations

from functools import wraps
import json
import mimetypes
import os
from pathlib import Path
import re
import shutil
import uuid

from django.conf import settings
from django.http import FileResponse, HttpResponse, JsonResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt

from egohand_twin.model import sha256
from egohand_twin.pipeline import probe

from . import services
from .models import ReviewDecision, Run, Video

API_VERSION = "1"
PRESETS = {
    "baseline": {"description": "MediaPipe defaults (historical B0); fastest",
                 "measured": "holdout recall 19/78, precision 19/19 (provisional labels, one clip)"},
    "recall": {"description": "Thresholds 0.3 + centre-crop rescue; about 2x detector time",
               "measured": "holdout recall 39/78, precision 39/40 (provisional labels, one clip); "
                           "more track fragmentation"},
}


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
            except (Video.DoesNotExist, Run.DoesNotExist, KeyError, FileNotFoundError) as error:
                return JsonResponse({"error": f"not found: {error}"}, status=404)
            except PermissionError as error:
                return JsonResponse({"error": str(error)}, status=403)
            if isinstance(result, (HttpResponse, StreamingHttpResponse)):
                return result
            return JsonResponse(result, safe=False, json_dumps_params={"separators": (",", ":")})
        return wrapper
    return decorator


def body(request) -> dict:
    try:
        data = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
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
    return {"presets": PRESETS, "default": "recall",
            "note": "Measurements are provisional (labels not yet human-reviewed) and from one clip."}


# --------------------------------------------------------------------------- videos
def register_video(path: Path) -> Video:
    existing = Video.objects.filter(path=str(path)).first()
    if existing:
        return existing
    info = probe(path)
    frames = len(info["timestamps"])
    return Video.objects.create(
        name=path.name, path=str(path), sha256=sha256(path), width=int(info["width"]), height=int(info["height"]),
        fps=info["fps"], frame_count=frames, duration_s=float(info["timestamps"][-1] - info["timestamps"][0]),
        timestamp_source=info["timestamp_source"])


@api(("GET", "POST"))
def videos(request):
    if request.method == "GET":
        return {"videos": [v.as_dict() for v in Video.objects.order_by("-created_at")]}
    path = body(request).get("path")
    if not path:
        raise ApiError("path is required (a file under EGOHAND_MEDIA_ROOTS)")
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


# --------------------------------------------------------------------------- runs
@api(("GET", "POST"))
def runs(request):
    if request.method == "GET":
        qs = Run.objects.select_related("video").all()
        if request.GET.get("video_id"):
            qs = qs.filter(video_id=request.GET["video_id"])
        if request.GET.get("status"):
            qs = qs.filter(status=request.GET["status"])
        return {"runs": [r.as_dict() for r in qs[:200]]}
    data = body(request)
    video = Video.objects.get(pk=data.get("video_id"))
    preset = data.get("preset", "recall")
    if preset not in PRESETS:
        raise ApiError(f"preset must be one of {sorted(PRESETS)}")
    start = float(data.get("start_s", 0.))
    duration = data.get("duration_s")
    duration = float(duration) if duration is not None else None
    if start < 0 or start >= video.duration_s + 1/video.fps:
        raise ApiError("start_s outside the video")
    if duration is not None and duration <= 0:
        raise ApiError("duration_s must be positive")
    workers = int(data.get("workers", 1))
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
        if run.status in (Run.Status.QUEUED, Run.Status.RUNNING):
            raise ApiError("cancel the run before deleting it", 409)
        if run.out_dir and Path(run.out_dir).resolve().parent == settings.RUNS_DIR.resolve():
            shutil.rmtree(run.out_dir, ignore_errors=True)  # only directories this backend created
        run.delete()
        return HttpResponse(status=204)
    data = run.as_dict(detail=True)
    data["video"] = run.video.as_dict()
    return data


@api(("POST",))
def run_cancel(request, run_id):
    updated = Run.objects.filter(pk=run_id, status__in=[Run.Status.QUEUED, Run.Status.RUNNING]).update(
        status=Run.Status.CANCELLED)
    if not updated:
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
    return services.read_frame(run_dir(Run.objects.get(pk=run_id)), frame_index, detail)


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
    if item_id not in {q["item_id"] for q in queue}:
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
def run_artifact(request, run_id, name: str):
    """Download whitelisted run files (exports) for analysis."""
    allowed = {"landmarks.jsonl", "landmarks.csv", "landmarks.npz", "manifest.json", "metrics.json",
               "tracking_events.csv", "replay.rrd", "quality/review_queue.csv", "quality/quality_frames.csv"}
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
    from egohand_twin.compare import compare, find_frame
    run = Run.objects.select_related("video").get(pk=run_id)
    directory = run_dir(run)
    t = number(request, "t")
    if t is None:
        raise ApiError("t (seconds on the run time base) is required")
    try:
        record = find_frame(directory, time_s=t)
    except ValueError as error:
        raise ApiError(str(error), 404)
    out = directory/"compare"/f"frame_{record['frame_index']:06d}.png"
    if not out.exists():
        compare(Path(run.video.path), directory, out, frame_index=record["frame_index"])
    response = FileResponse(out.open("rb"), content_type="image/png")
    response["Cache-Control"] = "private, max-age=86400"
    return response
