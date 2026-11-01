import pytest

from egohand_twin.parallel import PrecomputedDetector, plan_chunks


def test_chunks_are_contiguous_complete_and_warmed_up():
    frames = list(range(100, 130))
    plans = plan_chunks(frames, 3, overlap=4)
    kept = [i for p in plans for i in p["keep"]]
    assert kept == frames  # every frame exactly once, in order
    assert plans[0]["warmup"] == []
    assert plans[1]["warmup"] == [106, 107, 108, 109] and plans[1]["keep"][0] == 110
    assert plans[2]["warmup"] == [116, 117, 118, 119]


def test_more_workers_than_frames_and_stride_gaps():
    plans = plan_chunks([0, 2, 4], 8, overlap=15)
    assert [p["keep"] for p in plans] == [[0], [2], [4]]
    assert plans[2]["warmup"] == [0, 2]  # warm-up never reaches before the first processed frame


def test_precomputed_detector_refuses_missing_frames():
    d = PrecomputedDetector({0.033333: ["hand"]}, {})
    assert d.detect(None, 1/30) == ["hand"]
    with pytest.raises(RuntimeError, match="no precomputed"):
        d.detect(None, 2/30)


def _det(x):
    import numpy as np
    from egohand_twin.model import Detection
    image = np.zeros((21, 3))
    image[:, 0] = x
    return Detection(image, np.zeros((21, 3)), "Left", .9)


def test_lookahead_planned_except_last_chunk():
    plans = plan_chunks(list(range(30)), 3, overlap=2, lookahead=4)
    assert plans[0]["lookahead"] == [10, 11, 12, 13] and plans[2]["lookahead"] == []


def test_merge_repairs_seam_until_chunks_agree():
    from egohand_twin.parallel import merge_chunks
    a = {"chunk": 0, "detections": {0: [_det(.1)], 1: [_det(.1)]},
         "lookahead": {2: [_det(.2)], 3: [_det(.3)], 4: [_det(.4)], 5: [_det(.5)]}}
    # The next chunk disagrees on frame 2 (cold MediaPipe state), then agrees from frame 3.
    b = {"chunk": 1, "detections": {2: [], 3: [_det(.3)], 4: [_det(.4)], 5: [_det(.5)], 6: [_det(.6)]},
         "lookahead": {}}
    merged, seams = merge_chunks([b, a], agree=2)
    assert len(merged[2]) == 1 and merged[2][0].image[0, 0] == .2  # repaired from the previous chunk
    assert merged[6][0].image[0, 0] == .6
    assert seams == [{"after_chunk": 0, "converged": True, "frames_from_previous_chunk": 1, "lookahead_frames": 4}]


def test_merge_reports_unconverged_seam():
    from egohand_twin.parallel import merge_chunks
    a = {"chunk": 0, "detections": {0: []}, "lookahead": {1: [_det(.1)], 2: [_det(.2)]}}
    b = {"chunk": 1, "detections": {1: [], 2: [], 3: []}, "lookahead": {}}
    merged, seams = merge_chunks([a, b], agree=2)
    assert len(merged[1]) == 1 and len(merged[2]) == 1 and merged[3] == []
    assert seams[0]["converged"] is False and seams[0]["frames_from_previous_chunk"] == 2


def test_precomputed_detector_reports_worker_latency():
    d = PrecomputedDetector({0.1: []}, {0.1: .05})
    assert d.reported_latency(.1, 1e-6) == .05
    assert d.reported_latency(.2, 1e-6) == 1e-6


def test_lookahead_never_spans_beyond_the_next_chunk_and_merge_survives():
    from egohand_twin.parallel import merge_chunks
    plans = plan_chunks(list(range(20)), 4, overlap=2, lookahead=60)  # 5-frame chunks
    assert [p["lookahead"] for p in plans] == [[5, 6, 7, 8, 9], [10, 11, 12, 13, 14], [15, 16, 17, 18, 19], []]
    results = [{"chunk": p["chunk"], "detections": {f: [_det(.01*f + .001*p["chunk"])] for f in p["keep"]},
                "lookahead": {f: [_det(.5)] for f in p["lookahead"]}} for p in plans]  # never agree
    merged, seams = merge_chunks(results, agree=5)
    assert sorted(merged) == list(range(20)) and not any(s["converged"] for s in seams)


def test_process_args_raises_value_error_not_system_exit():
    from egohand_twin.cli import process_args
    with pytest.raises(ValueError):
        process_args(["v.mp4", "--out", "o", "--preset", "nonsense"])
    with pytest.raises(ValueError, match="workers"):
        process_args(["v.mp4", "--out", "o", "--workers", "0"])
    with pytest.raises(ValueError, match="detection_threshold"):
        process_args(["v.mp4", "--out", "o", "--detection-threshold", "2"])


def test_backward_pass_runs_segments_in_reverse_with_warmup(monkeypatch):
    """Each segment is detected newest-first, warmed up on the frames after it, and only kept
    frames are recorded; reverse timestamps increase strictly within each detector."""
    import argparse
    from egohand_twin import parallel
    calls = []

    class Fake:
        def __init__(self):
            self.times = []

        def detect(self, rgb, t, full=None):
            assert not self.times or t > self.times[-1]
            self.times.append(t)
            calls.append(rgb)
            return [rgb]

        def close(self):
            pass
    monkeypatch.setattr("egohand_twin.pipeline.build_detector", lambda args: Fake())
    keep = set(range(0, 10))
    bp = parallel.BackwardPass(argparse.Namespace(), keep, segment=4, warmup=2)
    for i in range(12):  # frames 10, 11 are the chunk's lookahead (warm-up only)
        bp.add(i, i, i/30)
    bp.flush()
    assert sorted(bp.results) == list(range(10))
    assert all(bp.results[i] == [i] for i in keep)
    assert calls[:6] == [5, 4, 3, 2, 1, 0]  # first segment 0-3, warmed up on 5, 4
    assert len(bp.buffer) == 0


def test_add_backward_adds_only_missing_non_duplicate_hands():
    import numpy as np
    from egohand_twin.model import Detection
    from egohand_twin.parallel import add_backward

    def hand(x):  # a hand-sized spread of landmarks around x
        image = np.zeros((21, 3))
        image[:, 0] = x + np.linspace(0, .08, 21)
        image[:, 1] = .5 + np.linspace(0, .12, 21)
        return Detection(image, np.zeros((21, 3)), "Left", .9)
    merged = add_backward([hand(.2)], [hand(.2), hand(.7)], 960, 540, num_hands=2)
    assert len(merged) == 2 and merged[1].image[0, 0] == .7  # the duplicate at .2 was skipped
    assert merged[1].origin_detail == "backward_pass" and merged[1].index == 1
    assert len(add_backward([hand(.2), hand(.5)], [hand(.8)], 960, 540, num_hands=2)) == 2


def test_accurate_preset_enables_the_backward_pass():
    from egohand_twin.cli import process_args
    assert process_args(["v.mp4", "--out", "o", "--preset", "accurate"]).bidirectional is True
    assert not process_args(["v.mp4", "--out", "o", "--preset", "recall"]).bidirectional
