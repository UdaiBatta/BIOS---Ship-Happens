import numpy as np

from egohand_twin.render import RerunSink, color, composite, hand_label


def test_overlay_keeps_unknown_side_distinct_from_right():
    assert color({"observed": True, "side": "Left"}) == (38, 89, 217)
    assert color({"observed": True, "side": "Right"}) == (229, 135, 57)
    assert color({"observed": True, "side": "unknown"}) == (129, 135, 137)
    assert color({"observed": False, "side": "Right"}) == (145, 145, 145)


def hand(state, observed, reason=None, p=.2):
    image = (np.tile([[.5, .5, 0.]], (21, 1)) + np.linspace(0, .05, 21)[:, None]).tolist() \
        if state in ("observed", "predicted") else None
    return {"track_id": 3, "state": state, "observed": observed, "side": "Left",
            "side_probability_right_smoothed": p, "missing_reason": reason,
            "missing_reason_basis": "test basis" if reason else None,
            "image_xyz": image, "image_xyz_raw": image if observed else None,
            "world_xyz_m": (np.random.default_rng(0).normal(0, .03, (21, 3))).tolist() if observed else None}


def test_hand_label_shows_side_probability_state_and_reason():
    assert hand_label(hand("observed", True)) == "#3 Left p_R=0.20 observed"
    assert hand_label(hand("predicted", False, "unknown")) == "#3 Left p_R=0.20 predicted 2D-only (unknown)"
    assert hand_label(hand("lost", False, "out_of_view")).endswith("lost (out_of_view)")
    legacy = {"track_id": 1, "state": "observed", "side": "Right"}  # runs from before schema 0.3
    assert hand_label(legacy) == "#1 Right observed"


def test_preview_and_rerun_accept_missing_states(tmp_path):
    frame = np.zeros((90, 160, 3), np.uint8)
    samples = [{"frame_index": i, "timestamp_s": i/10, "hands": [h]} for i, h in enumerate(
        [hand("observed", True), hand("predicted", False, "unknown"), hand("lost", False, "out_of_view")])]
    for s in samples:
        assert composite(frame, s).shape == (900, 1600, 3)
    sink = RerunSink(tmp_path/"r.rrd")
    for s in samples:
        sink.write(frame, s)
    sink.close()
    assert (tmp_path/"r.rrd").stat().st_size > 0
