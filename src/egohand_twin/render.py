from __future__ import annotations

from pathlib import Path
import json
import shutil
import subprocess

import cv2
import numpy as np

from .model import CONNECTIONS, sha256

BG, PANEL, TEXT, MUTED = (20, 16, 12), (34, 29, 23), (240, 238, 225), (160, 151, 136)


def color(hand):
    if not hand["observed"]:
        return (145, 145, 145)
    return (155, 216, 63) if hand["side"] == "Left" else (66, 171, 255)


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


def overlay(frame, hands):
    image = frame.copy()
    h, w = image.shape[:2]
    for hand in hands:
        if hand["image_xyz"] is None:
            continue
        points = np.asarray(hand["image_xyz"])[:, :2] * [w, h]
        draw_hand(image, points, color(hand), max(2, w//300), not hand["observed"])
        anchor = np.clip(points[0].astype(int), [0, 25], [w-250, h-10])
        text(image, f'#{hand["track_id"]} {hand["side"]} {hand["state"]}',
             int(anchor[0]), int(anchor[1]), .55, color(hand), 2)
    return image


def fit_image(image, width, height):
    h, w = image.shape[:2]
    scale = min(width/w, height/h)
    small = cv2.resize(image, (round(w*scale), round(h*scale)))
    canvas = np.full((height, width, 3), BG, np.uint8)
    x, y = (width-small.shape[1])//2, (height-small.shape[0])//2
    canvas[y:y+small.shape[0], x:x+small.shape[1]] = small
    return canvas


def composite(frame, sample):
    canvas = np.full((900, 1600, 3), BG, np.uint8)
    text(canvas, "EGOHAND TWIN", 28, 47, 1.15, TEXT, 2)
    text(canvas, "FACTORY POV  /  MEDIAPIPE BASELINE", 30, 78, .55, MUTED)
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
        text(canvas, f'#{hand["track_id"]} {hand["side"]}: {hand["state"]}',
             x+23, 756, .52, color(hand))
    if not sample["hands"]:
        text(canvas, "No active tracks", 28, 756, .55, MUTED)
    text(canvas, "Solid = observed   Dashed gray = short 2D prediction   Lost = hidden", 28, 803, .55, MUTED)
    text(canvas, "Hand-relative 3D estimates. Factory position and camera motion are not reconstructed.",
         28, 864, .57, TEXT)
    return canvas


class VideoSink:
    def __init__(self, path: Path, fps: float):
        if not shutil.which("ffmpeg"):
            raise RuntimeError("FFmpeg is required for H.264 previews; install it or use --no-video")
        self.process = subprocess.Popen([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
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
    def __init__(self, path: Path, lift: dict | None = None):
        """``lift`` optionally maps (frame_index, track_id) -> 21x3 camera-space joints from
        ``egohand lift``; it is shown in its own EXPERIMENTAL view, never mixed with the
        hand-relative view."""
        import rerun as rr
        import rerun.blueprint as rrb
        self.rr = rr
        self.lift = lift
        rr.init("egohand_twin", spawn=False)
        rr.save(str(path))
        views = [rrb.Spatial2DView(origin="video", name="Source + 2D"),
                 rrb.Spatial3DView(origin="hands", name="Hand-relative 3D; spacing arbitrary",
                                   eye_controls=rrb.EyeControls3D(
                                       kind=rrb.Eye3DKind.Orbital,
                                       position=(0., -.05, -.65),
                                       look_target=(0., -.05, 0.), eye_up=(0., -1., 0.)),
                                   line_grid=False)]
        if lift is not None:
            views.append(rrb.Spatial3DView(
                origin="camera_space", name=f"EXPERIMENTAL camera space ({lift['label']})",
                eye_controls=rrb.EyeControls3D(kind=rrb.Eye3DKind.Orbital, position=(.6, -.6, -.5),
                                               look_target=(0., 0., .45), eye_up=(0., -1., 0.))))
        rr.send_blueprint(rrb.Blueprint(rrb.Vertical(
            rrb.Horizontal(*views),
            rrb.TextLogView(origin="reliability", name="Tracking events"),
            row_shares=[4, 1]), rrb.TimePanel(timeline="video_time"), collapse_panels=True))
        rr.log("hands", rr.ViewCoordinates.RDF, static=True)
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
            if self.previous_states.get(key) != hand["state"]:
                rr.log("reliability", rr.TextLog(
                    f'#{key} {hand["side"]}: {hand["state"]}; 3D is hand-relative; spacing arbitrary'))
            self.previous_states[key] = hand["state"]

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


def rebuild_replay(video: Path, run: Path, output: Path, lift: Path | None = None):
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
    sink = RerunSink(output, load_lift(lift) if lift else None)
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
