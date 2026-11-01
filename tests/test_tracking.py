import numpy as np
import pytest

from motioniq.model import Detection, map_crop_detection
from motioniq.tracking import IdentityTracker, OneEuro


def detection(x=.3, y=.5, side="Left", score=.95):
    image = np.zeros((21, 3))
    image[:, 0] = x + np.linspace(0., .04, 21)
    image[:, 1] = y - np.linspace(0., .1, 21)
    world = (image-image.mean(axis=0)) * .4
    return Detection(image, world, side, score)


def test_result_order_swap_keeps_ids_and_soft_handedness():
    tracker = IdentityTracker()
    first = tracker.update([detection(.25), detection(.75, side="Right")], 0.)
    # Model order reverses and one handedness classification flips.
    second = tracker.update([detection(.74, side="Right"), detection(.26, side="Right")], .033)
    assert [(h["track_id"], h["side"]) for h in first] == [(1, "Left"), (2, "Right")]
    assert [(h["track_id"], h["side"]) for h in second] == [(1, "Left"), (2, "Right")]
    assert second[0]["raw_side"] == "Right"


def test_occlusion_is_not_a_3d_observation_and_can_recover():
    tracker = IdentityTracker()
    tracker.update([detection()], 0.)
    predicted = tracker.update([], .1)[0]
    assert predicted["state"] == "predicted"
    assert not predicted["observed"]
    assert predicted["world_xyz_m"] is None
    assert predicted["image_xyz_raw"] is None
    lost = tracker.update([], .3)[0]
    assert lost["state"] == "lost" and lost["image_xyz"] is None
    recovered = tracker.update([detection(.31)], .4)[0]
    assert recovered["track_id"] == 1 and recovered["state"] == "reacquired"


def test_expired_or_distant_reentry_receives_new_id():
    tracker = IdentityTracker()
    tracker.update([detection()], 0.)
    states = tracker.update([detection(.9)], .033)
    assert [s["track_id"] for s in states if s["observed"]] == [2]
    states = tracker.update([detection()], 2.)
    assert [s["track_id"] for s in states if s["observed"]] == [3]
    assert len([s for s in states if s["state"] == "retired"]) == 2


def test_tracks_through_crossing_without_result_index_dependency():
    tracker = IdentityTracker(smoothing=False)
    for frame in range(15):
        a, b = .3 + frame*.025, .7-frame*.025
        observations = [detection(a), detection(b, y=.55, side="Right")]
        if frame % 2:
            observations.reverse()
        hands = tracker.update(observations, frame/30)
        observed = {h["track_id"]: h for h in hands if h["observed"]}
        assert set(observed) == {1, 2}
        assert observed[1]["image_xyz_raw"][0][0] == pytest.approx(a)


def test_smoothing_preserves_raw_measurements():
    tracker = IdentityTracker()
    tracker.update([detection()], 0.)
    d = detection(.34)
    original = d.image.copy()
    hand = tracker.update([d], .033)[0]
    np.testing.assert_array_equal(d.image, original)
    assert hand["image_xyz_raw"][0][0] == .34
    assert hand["image_xyz"][0][0] < .34


def test_empty_and_nonmonotonic_timestamps():
    tracker = IdentityTracker()
    assert tracker.update([], 0.) == []
    with pytest.raises(ValueError):
        tracker.update([], 0.)


def test_filter_resets_after_long_gap():
    f = OneEuro()
    f(np.zeros(3), 0.)
    np.testing.assert_array_equal(f(np.ones(3), 1.), np.ones(3))


def test_crop_coordinates_and_depth_return_to_source_frame():
    d = detection(.4, .5)
    d.image[:, 2] = -.1
    original = d.image.copy()
    mapped = map_crop_detection(d, (100, 50, 300, 350), 400, 400)
    assert mapped.image[0, 0] == pytest.approx(.45)
    assert mapped.image[0, 1] == pytest.approx(.5)
    assert mapped.image[0, 2] == pytest.approx(-.05)
    np.testing.assert_array_equal(mapped.world, d.world)
    np.testing.assert_array_equal(d.image, original)
    assert mapped.origin == "center_crop_rescue"


def test_diagonal_units_treat_pixels_isotropically():
    def ids(tracker, dx, dy):
        tracker.update([detection(.5, .5)], 0.)
        return [h["track_id"] for h in tracker.update([detection(.5+dx, .5+dy)], 1/30) if h["observed"]]
    # 162 px vertical move on 1920x1080: legacy normalized units over-penalise it.
    assert ids(IdentityTracker(), 0., .15) == [2]
    assert ids(IdentityTracker(frame_size=(1920, 1080)), 0., .15) == [1]
    # 288 px horizontal move is rejected in both unit systems.
    assert ids(IdentityTracker(frame_size=(1920, 1080)), .15, 0.) == [2]


def test_missing_reason_out_of_view_unknown_and_observed():
    tracker = IdentityTracker(smoothing=False)
    # Hand moving right towards the border: extrapolated wrist leaves the image.
    for i, x in enumerate([.90, .94, .975]):
        hands = tracker.update([detection(x, .5)], i/30)
    assert hands[0]["missing_reason"] is None and hands[0]["observed"]
    gone = tracker.update([], 4/30)[0]
    assert gone["state"] == "predicted" and gone["missing_reason"] == "out_of_view"
    assert gone["missing_reason_provenance"] == "inferred" and "outside the image" in gone["missing_reason_basis"]
    # Hand in the middle of the image that stops being detected: no evidence -> unknown.
    tracker = IdentityTracker(smoothing=False)
    tracker.update([detection(.4, .5)], 0.)
    lost = tracker.update([], .3)[0]
    assert lost["state"] == "lost" and lost["missing_reason"] == "unknown"
    assert lost["image_xyz"] is None and lost["world_xyz_m"] is None


def test_missing_reason_border_touch_without_motion():
    tracker = IdentityTracker(smoothing=False)
    d = detection(.5, .99)  # wrist at the bottom border, not moving
    tracker.update([d], 0.)
    rec = tracker.update([], .1)[0]
    assert rec["missing_reason"] == "out_of_view"
    assert "touched the image border" in rec["missing_reason_basis"]


def test_presets_fill_only_unset_options():
    import argparse
    from motioniq.cli import apply_preset
    base = dict(detection_threshold=None, presence_threshold=None, tracking_threshold=None, rescue_crop=None)
    recall = apply_preset(argparse.Namespace(preset="recall", **base))
    assert (recall.detection_threshold, recall.rescue_crop) == (.3, True)
    baseline = apply_preset(argparse.Namespace(preset="baseline", **base))
    assert (baseline.detection_threshold, baseline.rescue_crop) == (.5, False)
    tiles = apply_preset(argparse.Namespace(preset="recall", rescue="tiles", **base))
    assert tiles.rescue_crop is False and tiles.detection_threshold == .3
    override = apply_preset(argparse.Namespace(preset="recall", **{**base, "detection_threshold": .4}))
    assert (override.detection_threshold, override.presence_threshold) == (.4, .3)


def _box_hand(x, y=.5, size=.1, side="Left"):
    import numpy as np
    from motioniq.model import Detection
    image = np.zeros((21, 3))
    image[:, 0] = x + np.linspace(0, size, 21)
    image[:, 1] = y + np.linspace(0, size, 21)
    return Detection(image, np.zeros((21, 3)), side, .9)


def test_box_link_hides_a_predicted_ghost_on_an_observed_hand():
    from motioniq.tracking import IdentityTracker
    for box_link, expected in ((False, "predicted"), (True, "lost")):
        t = IdentityTracker(box_link=box_link)
        first = t.update([_box_hand(.20), _box_hand(.24)], 0.)   # two overlapping tracks
        ghost = [r["track_id"] for r in first][1]
        second = t.update([_box_hand(.205)], 1/30)                # one hand observed now
        state = {r["track_id"]: r["state"] for r in second}
        assert state[ghost] == expected
        assert sum(s == "observed" for s in state.values()) == 1


def test_box_link_keeps_one_identity_when_the_wrist_jumps_inside_the_same_hand_box():
    import numpy as np
    from motioniq.tracking import IdentityTracker
    t = IdentityTracker(box_link=True)
    tid = t.update([_box_hand(.30, size=.3)], 0.)[0]["track_id"]
    moved = _box_hand(.30, size=.3)
    moved.image[0, :2] += [.2, .2]                             # wrist placed elsewhere in the same hand box
    out = t.update([moved], 1/30)
    assert [r["track_id"] for r in out if r["state"] == "observed"] == [tid] and t.box_links == 1
