import numpy as np
import pytest

from egohand_twin.model import Detection, map_crop_detection
from egohand_twin.tracking import IdentityTracker, OneEuro


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
