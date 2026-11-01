import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

spec = importlib.util.spec_from_file_location(
    "render_common_deliverables", Path(__file__).parents[1] / "scripts" / "render_common_deliverables.py")
deliverables = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deliverables)


def make_cached_run(tmp_path, *, source_hash=None, preset="accurate", stride=1, complete=True):
    video = tmp_path / "source.mp4"
    video.write_bytes(b"synthetic video")
    source_hash = source_hash or hashlib.sha256(video.read_bytes()).hexdigest()
    run = tmp_path / "runs" / "C1" / "accurate"
    run.mkdir(parents=True)
    if complete:
        (run / "COMPLETE").write_text("complete\n")
    (run / "manifest.json").write_text(json.dumps({
        "source": {"sha256": source_hash, "fps": 30, "cfr": True},
        "parameters": {"preset": preset, "stride": stride},
    }))
    records = [
        {"frame_index": 0, "timestamp_s": 0., "hands": []},
        {"frame_index": 1, "timestamp_s": 1 / 30, "hands": []},
    ]
    (run / "landmarks.jsonl").write_text("".join(json.dumps(row) + "\n" for row in records))
    clip = {
        "clip_id": "C1", "source_sha256": source_hash,
        "selected_interval": {"start_seconds": 0., "end_seconds": 1.},
        "runs": {"accurate": {"status": "complete", "metrics": {
            "processed_frames": len(records), "processing_seconds": 2.,
            "observed_hand_frames": 1, "observed_hands": 2,
        }}}
    }
    return video, clip, run


def test_source_hash_matches_summary_and_manifest_before_render(tmp_path):
    video, clip, _ = make_cached_run(tmp_path)
    evaluator = deliverables.load_evaluator()
    match = deliverables.match_videos([video], [clip], evaluator)
    metadata = deliverables.prepare_task(match[0][0], match[0][1], tmp_path / "runs", "accurate")
    assert metadata["clip_id"] == "C1"
    assert metadata["frame_count"] == 2
    assert "records" not in metadata
    task = deliverables.load_task(metadata)
    assert len(task["records"]) == 2


def test_source_binding_rejects_wrong_video_and_wrong_manifest_hash(tmp_path):
    video, clip, run = make_cached_run(tmp_path)
    evaluator = deliverables.load_evaluator()
    clip["source_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="source hash"):
        deliverables.match_videos([video], [clip], evaluator)

    clip["source_sha256"] = evaluator.sha256(video)
    manifest = json.loads((run / "manifest.json").read_text())
    manifest["source"]["sha256"] = "1" * 64
    (run / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="source hash"):
        deliverables.prepare_task(video, clip, tmp_path / "runs", "accurate")


@pytest.mark.parametrize("preset,stride", [("recall", 1), ("accurate", 2)])
def test_cached_manifest_must_match_selected_preset_and_stride(tmp_path, preset, stride):
    video, clip, _ = make_cached_run(tmp_path, preset=preset, stride=stride)
    with pytest.raises(ValueError, match="preset|stride"):
        deliverables.prepare_task(video, clip, tmp_path / "runs", "accurate")


def test_cached_run_requires_completion_marker_and_nonempty_frames(tmp_path):
    video, clip, run = make_cached_run(tmp_path, complete=False)
    with pytest.raises(ValueError, match="completion marker"):
        deliverables.prepare_task(video, clip, tmp_path / "runs", "accurate")
    (run / "COMPLETE").write_text("complete\n")
    (run / "landmarks.jsonl").write_text("\n")
    with pytest.raises(ValueError, match="no landmark frames"):
        deliverables.prepare_task(video, clip, tmp_path / "runs", "accurate")


@pytest.mark.parametrize("info,match", [
    ({"streams": [{"codec_name": "mpeg4", "pix_fmt": "yuv420p", "duration": "1", "nb_read_packets": "2"}]}, "codec"),
    ({"streams": [{"codec_name": "h264", "pix_fmt": "yuv444p", "duration": "1", "nb_read_packets": "2"}]}, "codec"),
    ({"streams": [{"codec_name": "h264", "pix_fmt": "yuv420p", "duration": "1", "nb_read_packets": "1"}]}, "frame count"),
    ({"streams": [{"codec_name": "h264", "pix_fmt": "yuv420p", "duration": "0", "nb_read_packets": "2"}]}, "duration"),
])
def test_encoded_video_must_be_h264_yuv420p_with_matching_packets(info, match):
    with pytest.raises(ValueError, match=match):
        deliverables.validate_encoded(info, 2)


def test_render_task_decodes_sequentially_and_publishes_after_probe(tmp_path, monkeypatch):
    video = tmp_path / "source.mp4"
    video.touch()
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    reads = []

    class Capture:
        def __init__(self, path):
            self.index = 0

        def isOpened(self):
            return True

        def read(self):
            value = self.index
            self.index += 1
            reads.append(value)
            return True, np.full((2, 2, 3), value, dtype=np.uint8)

        def release(self):
            pass

    class Sink:
        def __init__(self, path, fps):
            self.path = path
            self.frames = []

        def write(self, frame):
            self.frames.append(frame)

        def close(self):
            self.path.write_bytes(b"verified synthetic mp4")

    rendered = []
    monkeypatch.setattr(deliverables.cv2, "VideoCapture", Capture)
    monkeypatch.setattr(deliverables, "VideoSink", Sink)
    monkeypatch.setattr(deliverables, "composite", lambda frame, sample, subtitle: rendered.append((int(frame[0, 0, 0]), subtitle)) or frame)
    monkeypatch.setattr(deliverables, "encoded_info", lambda path: {"streams": [{
        "codec_name": "h264", "pix_fmt": "yuv420p", "duration": "1", "nb_read_packets": "1"}]})
    task = {"clip_id": "C1", "video": video, "records": [{"frame_index": 2, "timestamp_s": .1, "hands": []}], "fps": 30.}

    result = deliverables.render_task(task, output_dir, "accurate")

    assert reads == [0, 1, 2]
    assert rendered == [(2, "C1 / accurate / labels not reviewed / estimated 3D")]
    assert result["filename"] == "C1_accurate.mp4"
    assert result["bytes"] == len(b"verified synthetic mp4")
    assert (output_dir / result["filename"]).read_bytes() == b"verified synthetic mp4"


def test_existing_deliverables_are_never_overwritten(tmp_path):
    target = tmp_path / "C1_accurate.mp4"
    readme = tmp_path / "README.txt"
    target.write_bytes(b"keep this file")
    readme.write_text("keep this readme")

    with pytest.raises(ValueError, match="already exists"):
        deliverables.ensure_outputs_unused([target], readme)

    assert target.read_bytes() == b"keep this file"
    assert readme.read_text() == "keep this readme"


def test_atomic_publish_fails_if_target_appears(tmp_path):
    temporary = tmp_path / "render.tmp.mp4"
    target = tmp_path / "final.mp4"
    temporary.write_bytes(b"new")
    target.write_bytes(b"existing")

    with pytest.raises(FileExistsError):
        deliverables.publish_file(temporary, target)

    assert temporary.read_bytes() == b"new"
    assert target.read_bytes() == b"existing"


def test_readme_uses_neutral_ids_and_separates_inference_from_render(tmp_path):
    task = {"clip_id": "C1", "interval": (0., 1.), "frame_count": 2,
            "observed_frames": 1, "observed_hands": 2, "processing_seconds": 2.}
    output = {"filename": "C1_accurate.mp4", "bytes": 64, "render_seconds": 3.}
    target = tmp_path / "README.txt"

    deliverables.write_readme(target, "accurate", [(task, output)])

    text = target.read_text()
    assert "C1" in text and "not reviewed" in text
    assert "does not claim the preset is best" in text
    assert "2.00" in text and "3.00" in text
    assert "source.mp4" not in text


@pytest.mark.parametrize("cfr", [False, None])
def test_fixed_fps_renderer_rejects_variable_or_unknown_source_timing(tmp_path, cfr):
    video, clip, run = make_cached_run(tmp_path)
    path = run / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["source"]["cfr"] = cfr
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="constant frame rate"):
        deliverables.prepare_task(video, clip, tmp_path / "runs", "accurate")
