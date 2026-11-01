from __future__ import annotations

from pathlib import Path
import json
import subprocess

import cv2
import numpy as np

from .model import CONNECTIONS, sha256
from .ffmpeg import require_tool

BG, PANEL, TEXT, MUTED = (20, 16, 12), (34, 29, 23), (240, 238, 225), (160, 151, 136)


def color(hand):
    if not hand["observed"]:
        return (145, 145, 145)
    return {"Left": (38, 89, 217), "Right": (229, 135, 57)}.get(hand["side"], (129, 135, 137))


def text(canvas, value, x, y, size=.6, c=TEXT, thickness=1):
    cv2.putText(canvas, str(value), (x, y), cv2.FONT_HERSHEY_SIMPLEX, size,
                c, thickness, cv2.LINE_AA)


def draw_hand(canvas, points, c, radius=4, predicted=False):
    points = np.asarray(points).round().astype(int)
    points = np.clip(points, -10000, 10000)
    for a, b in CONNECTIONS:
        if predicted:
            for t in np.arange(0., 1., .25):
                p = points[a] * (1-t) + points[b] * t
                q = points[a] * (1-min(1., t+.12)) + points[b] * min(1., t+.12)
                cv2.line(canvas, p.astype(int), q.astype(int), c, 1, cv2.LINE_AA)
        else:
            cv2.line(canvas, points[a], points[b], c, 2, cv2.LINE_AA)
    for point in points:
        cv2.circle(canvas, point, radius, c, -1, cv2.LINE_AA)


STATE_LANE = {"observed": "observed", "reacquired": "observed", "predicted": "predicted", "lost": "lost"}


def hand_label(hand) -> str:
    """Short reliability label: id, displayed side with right-probability, state, missing reason.

    p_R is the track's smoothed right-hand probability from the handedness classifier;
    it is side confidence only, never landmark or detection quality.
    """
    p = hand.get("side_probability_right_smoothed")
    side = f'{hand["side"]} p_R={p:.2f}' if p is not None else hand["side"]
    state = hand["state"] + (" 2D-only" if hand["state"] == "predicted" else "")
    reason = hand.get("missing_reason")
    return f'#{hand["track_id"]} {side} {state}' + (f" ({reason})" if reason else "")


def overlay(frame, hands):
    image = frame.copy()
    h, w = image.shape[:2]
    for hand in hands:
        if hand["image_xyz"] is None:
            continue
        points = np.asarray(hand["image_xyz"])[:, :2] * [w, h]
        draw_hand(image, points, color(hand), max(2, w//300), not hand["observed"])
        anchor = np.clip(points[0].astype(int), [0, 25], [w-int(420*max(1., w/960)), h-10])
        # Scale text with the frame so labels stay legible after fitting into the panel.
        scale = max(1., w/960)
        thickness = max(2, round(2*scale))
        text(image, hand_label(hand), int(anchor[0]), int(anchor[1]), .55*scale, (0, 0, 0), thickness+3)  # outline
        text(image, hand_label(hand), int(anchor[0]), int(anchor[1]), .55*scale, color(hand), thickness)
    return image


def fit_image(image, width, height):
    h, w = image.shape[:2]
    scale = min(width/w, height/h)
    small = cv2.resize(image, (round(w*scale), round(h*scale)))
    canvas = np.full((height, width, 3), BG, np.uint8)
    x, y = (width-small.shape[1])//2, (height-small.shape[0])//2
    canvas[y:y+small.shape[0], x:x+small.shape[1]] = small
    return canvas


def composite(frame, sample, subtitle="FACTORY POV  /  MEDIAPIPE HAND LANDMARKER"):
    canvas = np.full((900, 1600, 3), BG, np.uint8)
    text(canvas, "EGOHAND TWIN", 28, 47, 1.15, TEXT, 2)
    text(canvas, subtitle, 30, 78, .55, MUTED)
    text(canvas, f'{sample["timestamp_s"]:08.3f}s  |  frame {sample["frame_index"]}',
         1120, 45, .65, MUTED)
    text(canvas, "SOURCE + 2D LANDMARKS  /  ESTIMATED SIDE", 28, 115, .6, MUTED)
    canvas[132:672, 24:984] = fit_image(overlay(frame, sample["hands"]), 960, 540)
    cv2.rectangle(canvas, (1006, 132), (1576, 672), PANEL, -1)
    text(canvas, "3D HAND POSTURE", 1026, 165, .7, TEXT, 2)
    text(canvas, "WRIST-CENTERED  /  METERS (ESTIMATED)", 1026, 192, .45, MUTED)
    observed = [h for h in sample["hands"] if h["world_xyz_m"] is not None]
    for i, hand in enumerate(observed):
        world = np.asarray(hand["world_xyz_m"])
        world = world - world[0]
        # Isometric projection, same fixed scale for every frame and hand.
        projection = np.array([[.866, 0, .5], [-.20, 1., .346]])
        origin = np.array([1148 + i*265, 478.])
        points = world @ projection.T * 1250 + origin
        draw_hand(canvas, points, color(hand), 5)
        for axis, label in zip(np.eye(3)*.04, ["x", "y", "z"]):
            endpoint = origin + axis @ projection.T * 1250
            cv2.line(canvas, origin.astype(int), endpoint.astype(int), MUTED, 1, cv2.LINE_AA)
            text(canvas, label, int(endpoint[0]), int(endpoint[1]), .4, MUTED)
        text(canvas, f'#{hand["track_id"]}  {hand["side"]}', int(origin[0])-68, 588,
             .65, color(hand), 2)
    if not observed:
        text(canvas, "No observed 3D hand", 1110, 398, .7, MUTED)
    text(canvas, "Separate local origins; display spacing is arbitrary.", 1025, 642, .43, MUTED)
    text(canvas, "RELIABILITY", 28, 714, .6, MUTED)
    for i, hand in enumerate(sample["hands"][:5]):
        x = 28 + i * 307
        cv2.circle(canvas, (x+6, 749), 6, color(hand), -1)
        text(canvas, hand_label(hand), x+23, 756, .42, color(hand))
    if not sample["hands"]:
        text(canvas, "No active tracks", 28, 756, .55, MUTED)
    text(canvas, "Solid = observed   Dashed gray = short 2D prediction   Lost = no coordinates   "
                 "p_R = side probability (not landmark quality)", 28, 803, .5, MUTED)
    text(canvas, "Hand-relative 3D estimates. Factory position and camera motion are not reconstructed.",
         28, 864, .57, TEXT)
    return canvas


class VideoSink:
    def __init__(self, path: Path, fps: float):
        self.process = subprocess.Popen([
            require_tool("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y",
            "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", "1600x900", "-r", str(fps),
            "-i", "pipe:0", "-an", "-c:v", "libx264", "-preset", "veryfast",
            "-crf", "23", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(path),
        ], stdin=subprocess.PIPE)

    def write(self, frame):
        self.process.stdin.write(frame.tobytes())

    def close(self):
        self.process.stdin.close()
        if self.process.wait() != 0:
            raise RuntimeError("FFmpeg preview encoding failed")


class RerunSink:
    def __init__(self, path: Path, lift: dict | None = None, quality: dict | None = None,
                 steps: list | None = None):
        """``lift`` optionally maps (frame_index, track_id) -> 21x3 camera-space joints from
        ``egohand lift``; it is shown in its own EXPERIMENTAL view, never mixed with the
        hand-relative view."""
        import rerun as rr
        import rerun.blueprint as rrb
        self.rr = rr
        self.lift = lift
        self.quality = quality
        rr.init("egohand_twin", spawn=False)
        rr.save(str(path))
        views = [rrb.Spatial2DView(origin="video", name="Source + 2D (normalized image coords)"),
                 rrb.Spatial3DView(origin="hands", name="Hand-relative 3D (MediaPipe m, wrist-centred; spacing arbitrary)",
                                   eye_controls=rrb.EyeControls3D(
                                       kind=rrb.Eye3DKind.Orbital,
                                       position=(0., -.05, -.65),
                                       look_target=(0., -.05, 0.), eye_up=(0., -1., 0.)),
                                   line_grid=False)]
        if lift is not None:
            views.append(rrb.Spatial3DView(
                origin="camera_space",
                name=f"EXPERIMENTAL camera space (m; x right, y down, z forward; {lift['label']})",
                eye_controls=rrb.EyeControls3D(kind=rrb.Eye3DKind.Orbital, position=(.6, -.6, -.5),
                                               look_target=(0., 0., .45), eye_up=(0., -1., 0.))))
        bottom = [rrb.TimeSeriesView(origin="lanes", name="Track state lanes (y = track ID)"),
                  rrb.TextLogView(origin="reliability", name="Tracking events")]
        if quality is not None:
            bottom = [rrb.TimeSeriesView(origin="quality/signals", name="Quality signals (heuristic)"),
                      rrb.TextLogView(origin="quality/queue", name="Review queue"), *bottom]
        if steps is not None:
            bottom = [rrb.TextLogView(origin="steps", name="Steps (human-authored)"), *bottom]
        rr.send_blueprint(rrb.Blueprint(rrb.Vertical(
            rrb.Horizontal(*views),
            rrb.Horizontal(*bottom),
            row_shares=[3, 2] if quality is not None else [4, 1]),
            rrb.TimePanel(timeline="video_time"), collapse_panels=True))
        rr.log("hands", rr.ViewCoordinates.RDF, static=True)
        self.lane_styles: set = set()
        for i, step in enumerate(steps or [], 1):
            # Human-authored markers on the same time base as the video (timestamp_s).
            status = f"signed off by {step['reviewer']}" if step["signed_off"] else "NOT signed off"
            rr.set_time("video_time", duration=step["start_s"])
            rr.log("steps", rr.TextLog(
                f"STEP {i} start: {step['label']} (v{step['version']}, {status})"
                + (f" - {step['note']}" if step["note"] else ""), level="INFO"))
            rr.log("steps/active_step", rr.Scalars(i))
            rr.set_time("video_time", duration=step["end_s"])
            rr.log("steps", rr.TextLog(f"STEP {i} end: {step['label']}", level="DEBUG"))
            rr.log("steps/active_step", rr.Scalars(0))
        if lift is not None:
            rr.log("camera_space", rr.ViewCoordinates.RDF, static=True)
            # Simple frustum glyph at the camera origin (x right, y down, z forward).
            corners = np.array([[-.08, -.05, .1], [.08, -.05, .1], [.08, .05, .1], [-.08, .05, .1]])
            strips = [[[0, 0, 0], c] for c in corners] + [list(corners) + [corners[0]]]
            rr.log("camera_space/camera", rr.LineStrips3D(strips, colors=(200, 200, 200), radii=.002), static=True)
            rr.log("camera_space/note", rr.TextDocument(
                "Camera coordinates under an ASSUMED lens model; depth unvalidated; not factory coordinates."),
                static=True)
        self.previous_states = {}

    def write(self, frame, sample):
        rr = self.rr
        rr.set_time("video_time", duration=sample["timestamp_s"])
        rr.set_time("source_frame", sequence=sample["frame_index"])
        rgb = cv2.cvtColor(overlay(frame, sample["hands"]), cv2.COLOR_BGR2RGB)
        rr.log("video/image", rr.Image(rgb).compress(jpeg_quality=80))
        rr.log("hands", rr.Clear(recursive=True))
        if self.lift is not None:
            rr.log("camera_space/hands", rr.Clear(recursive=True))
            for hand in sample["hands"]:
                joints = self.lift["joints"].get((sample["frame_index"], hand["track_id"]))
                if joints is None:
                    continue
                c = color(hand)[::-1]
                root = f"camera_space/hands/track_{hand['track_id']}"
                rr.log(root+"/joints", rr.Points3D(joints, colors=c, radii=.004))
                rr.log(root+"/bones", rr.LineStrips3D(joints[np.asarray(CONNECTIONS)], colors=c, radii=.002))
        if self.quality is not None:
            row = self.quality["frames"].get(sample["frame_index"])
            if row is not None:
                rr.log("quality/signals/observed_hands", rr.Scalars(row["observed_hands"]))
                rr.log("quality/signals/blur_relative", rr.Scalars(row["blur_laplacian_var"]/self.quality["clip_blur"]))
                if row["camera_motion_rate"] not in (None, ""):
                    rr.log("quality/signals/camera_motion_pct_width_per_s_div100",
                           rr.Scalars(float(row["camera_motion_rate"])/100))
            for item in self.quality["starts"].get(sample["frame_index"], []):
                level = {"needs_review": "WARN", "insufficient_evidence": "INFO", "suitable": "DEBUG"}[item["status"]]
                reasons = ", ".join(f"{r}x{n}" for r, n in sorted(item["reason_window_counts"].items()))
                rr.log("quality/queue", rr.TextLog(
                    f'{item["item_id"]} {item["status"]} {item["start_s"]:.1f}-{item["end_s"]:.1f}s '
                    f'tracks {item["track_ids"]}: {reasons or "no flags"} [heuristic]', level=level))
        occupied_slots = set()
        for hand in sample["hands"]:
            key = hand["track_id"]
            if hand["world_xyz_m"] is not None:
                world = np.asarray(hand["world_xyz_m"])
                world -= world[0]
                slot = -.14 if hand["side"] == "Left" else .14
                if slot in occupied_slots:
                    slot = -slot
                occupied_slots.add(slot)
                world[:, 0] += slot  # Presentation offset only; never a root translation estimate.
                c = color(hand)[::-1]
                root = f"hands/track_{key}"
                rr.log(root+"/joints", rr.Points3D(world, colors=c, radii=.003))
                rr.log(root+"/bones", rr.LineStrips3D(
                    world[np.asarray(CONNECTIONS)], colors=c, radii=.0015))
            self._log_lane(hand)
            if self.previous_states.get(key) != hand["state"]:
                basis = hand.get("missing_reason_basis")
                rr.log("reliability", rr.TextLog(
                    hand_label(hand) + (f" - {basis}" if basis else "") +
                    ("; 3D is hand-relative; spacing arbitrary" if hand["observed"] else ""),
                    level="INFO" if hand["observed"] else "WARN"))
            self.previous_states[key] = hand["state"]

    def _log_lane(self, hand):
        """One horizontal lane per track (y = track ID). Points are coloured by state and,
        when observed, by displayed side; gaps mean the track is retired or not yet created."""
        rr = self.rr
        state = STATE_LANE.get(hand["state"])
        if state is None:
            return
        name = f'{state}_{hand["side"].lower()}' if state == "observed" else state
        path = f'lanes/track_{hand["track_id"]}/{name}'
        if path not in self.lane_styles:
            colours = {"observed_left": (63, 216, 155), "observed_right": (255, 171, 66),
                       "predicted": (145, 145, 145), "lost": (230, 70, 70)}
            rr.log(path, rr.SeriesPoints(colors=colours[name], names=f'#{hand["track_id"]} {name}',
                                         marker_sizes=2.), static=True)
            self.lane_styles.add(path)
        rr.log(path, rr.Scalars(float(hand["track_id"])))

    def close(self):
        self.rr.disconnect()


def load_lift(path: Path) -> dict:
    data = np.load(path, allow_pickle=False)
    joints = {}
    for i in np.flatnonzero(data["ok"]):
        joints[(int(data["frame_index"][i]), int(data["track_id"][i]))] = data["joints_cam_m"][i].astype(float)
    summary = path.with_suffix(".json")
    label = path.stem
    if summary.exists():
        camera = json.loads(summary.read_text())["camera"]
        label = f"assumed {camera['model']} HFOV {camera['hfov_deg']:g} deg"
    return {"joints": joints, "label": label}


def load_quality(directory: Path) -> dict:
    import csv
    frames = {}
    with (directory/"quality_frames.csv").open() as f:
        for row in csv.DictReader(f):
            frames[int(row["frame_index"])] = {
                "observed_hands": int(row["observed_hands"]),
                "blur_laplacian_var": float(row["blur_laplacian_var"]),
                "camera_motion_rate": float(row["camera_motion_rate"]) if row["camera_motion_rate"] else None}
    starts: dict[int, list] = {}
    for item in json.loads((directory/"review_queue.json").read_text()):
        starts.setdefault(item["first_frame"], []).append(item)
    clip_blur = float(np.median([r["blur_laplacian_var"] for r in frames.values()]))
    return {"frames": frames, "starts": starts, "clip_blur": clip_blur}


def rebuild_replay(video: Path, run: Path, output: Path, lift: Path | None = None,
                   quality: Path | None = None, steps: Path | None = None):
    """Re-render cached observations without running or changing the detector."""
    if not (run/"COMPLETE").exists():
        raise ValueError("Run is incomplete")
    if output.exists():
        raise ValueError("Replay output exists; choose a new filename")
    manifest = json.loads((run/"manifest.json").read_text())
    if sha256(video) != manifest["source"]["sha256"]:
        raise ValueError("Source video does not match the cached run")
    output.parent.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(str(video))
    from .steps import load_steps
    sink = RerunSink(output, load_lift(lift) if lift else None, load_quality(quality) if quality else None,
                     load_steps(steps, run) if steps else None)
    count = 0
    try:
        frame_index = -1
        with (run/"landmarks.jsonl").open() as f:
            for line in f:
                sample = json.loads(line)
                while frame_index < sample["frame_index"]:
                    ok, frame = cap.read()
                    if not ok:
                        raise ValueError("Video ended before the cached frame")
                    frame_index += 1
                h, w = frame.shape[:2]
                scale = min(1., manifest["parameters"]["max_width"]/w)
                image = cv2.resize(frame, (round(w*scale), round(h*scale))) if scale < 1 else frame
                sink.write(image, sample)
                count += 1
    finally:
        cap.release()
        sink.close()
    print(f"Replayed {count} cached frames to {output}")
