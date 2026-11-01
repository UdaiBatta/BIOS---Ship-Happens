"""Physical track identity is independent of the detector that produced the observation."""
import numpy as np

from motioniq.model import Detection
from motioniq.tracking import IdentityTracker

PRESET = dict(box_link=True, side_weights={"center_crop_rescue": 0.}, side_hysteresis=.15)


def hand(x, y=.5, origin="full_frame", detail=None, score=.95, side="Right"):
    image = np.zeros((21, 3))
    image[:, 0] = x + np.linspace(0, .08, 21)
    image[:, 1] = y + np.linspace(0, .12, 21)
    return Detection(image, np.zeros((21, 3)), side, score, origin=origin, origin_detail=detail)


def test_alternating_detectors_keep_one_track_and_side():
    """Test 7: MediaPipe, crop rescue and RTMPose alternate on one moving hand."""
    t = IdentityTracker(**PRESET)
    kinds = [("full_frame", None, .95), ("center_crop_rescue", None, .6), ("hand_detector", "rtmpose_fitted_3d", .5)]
    out = []
    for i in range(30):
        origin, detail, score = kinds[i % 3]
        side = "Left" if origin != "full_frame" else "Right"   # unreliable paths even disagree
        out.append(t.update([hand(.3 + .003*i, origin=origin, detail=detail, score=score, side=side)], i/30))
    obs = [r for f in out for r in f if r["observed"]]
    assert {r["track_id"] for r in obs} == {1} and {r["side"] for r in obs} == {"Right"}


def test_short_gap_reacquires_the_same_track():
    """Test 6: a hand hidden for 0.3 s comes back nearby as the same track."""
    t = IdentityTracker(**PRESET)
    first = t.update([hand(.3)], 0.)[0]["track_id"]
    for i in range(1, 10):
        t.update([], i/30)
    back = [r for r in t.update([hand(.31)], 10/30) if r["observed"]][0]
    assert back["track_id"] == first and back["state"] == "reacquired"


def test_long_absence_is_not_forced_into_the_old_track():
    """Test 6: after more than the retention time, a re-entering hand gets a new identity."""
    t = IdentityTracker(**PRESET)
    first = t.update([hand(.3)], 0.)[0]["track_id"]
    t.update([], .5)
    back = [r for r in t.update([hand(.3)], 1.5) if r["observed"]][0]
    assert back["track_id"] != first


def test_far_reentry_does_not_inherit_an_old_identity():
    t = IdentityTracker(**PRESET)
    first = t.update([hand(.1)], 0.)[0]["track_id"]
    back = [r for r in t.update([hand(.8)], 1/30) if r["observed"]][0]
    assert back["track_id"] != first


def test_record_count_never_exceeds_the_schema_limit_and_observations_survive():
    t = IdentityTracker(max_records=8)
    t.update([hand(.02 + .09*i, y=.1 + .2*(i % 3)) for i in range(10)], 0.)   # 10 tracks at once
    out = t.update([hand(.02, .1)], .5)                      # 9 are lost now, 1 observed
    assert len(out) <= 8 and sum(r["observed"] for r in out) == 1 and t.capacity_retired == 2
    out = t.update([hand(.02, .1)], .5 + 1/30)
    assert len(out) <= 8


def test_hand_that_stops_while_unseen_rejoins_its_track():
    """Fast hand, missed for a few frames, reappears where it was last seen (not where velocity says)."""
    t = IdentityTracker(**PRESET, last_position_link=True)
    for i in range(5):
        tid = [r for r in t.update([hand(.2 + .06*i)], i/30) if r["observed"]][0]["track_id"]
    for i in range(5, 11):
        t.update([], i/30)                                    # unseen 0.2 s; prediction runs ahead
    back = [r for r in t.update([hand(.44)], 11/30) if r["observed"]][0]
    assert back["track_id"] == tid and back["state"] == "reacquired" and t.last_position_links == 1
    plain = IdentityTracker(**PRESET)                         # without the link: a new identity
    for i in range(5):
        plain.update([hand(.2 + .06*i)], i/30)
    for i in range(5, 11):
        plain.update([], i/30)
    assert [r for r in plain.update([hand(.44)], 11/30) if r["observed"]][0]["track_id"] != tid
