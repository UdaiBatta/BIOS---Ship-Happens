"""Left/right identity: a track's side is not overwritten by single unreliable frames (Test 1)."""
import numpy as np

from egohand_twin.model import Detection
from egohand_twin.tracking import IdentityTracker

PRESET = dict(box_link=True, side_weights={"center_crop_rescue": 0.}, side_hysteresis=.15)


def hand(x, side="Right", score=.95, origin="full_frame", detail=None):
    image = np.zeros((21, 3))
    image[:, 0] = x + np.linspace(0, .08, 21)
    image[:, 1] = .5 + np.linspace(0, .12, 21)
    return Detection(image, np.zeros((21, 3)), side, score, origin=origin, origin_detail=detail)


def run(frames, **kw):
    tracker = IdentityTracker(**kw)
    return [tracker.update(d, i/30) for i, d in enumerate(frames)]


def sides(out):
    return [[r["side"] for r in frame if r["observed"]][0] for frame in out]


def test_cloth_hand_does_not_flip_on_contradicting_crop_frames():
    # 10 confident Right frames, then 6 centre-crop frames that say Left (as on the cloth hand)
    frames = [[hand(.3 + .002*i)] for i in range(10)]
    frames += [[hand(.32 + .002*i, side="Left", origin="center_crop_rescue")] for i in range(6)]
    assert set(sides(run(frames))[:10]) == {"Right"}
    assert sides(run(frames, **PRESET))[-1] == "Right"           # preset: crop evidence ignored
    assert sides(run(frames))[-1] == "Left"                       # old behaviour flipped


def test_single_contradicting_full_frame_does_not_flip_with_hysteresis():
    frames = [[hand(.3)] for _ in range(4)] + [[hand(.3, side="Left", score=.99)]] + [[hand(.3)] for _ in range(3)]
    out = run(frames, **PRESET)
    assert set(sides(out)) == {"Right"}
    ids = {[r["track_id"] for r in f if r["observed"]][0] for f in out}
    assert len(ids) == 1                                          # one physical hand, one track


def test_sustained_evidence_still_changes_the_side():
    frames = [[hand(.3)] for _ in range(3)] + [[hand(.3, side="Left", score=.99)] for _ in range(20)]
    assert sides(run(frames, **PRESET))[-1] == "Left"


def test_neutral_evidence_inherits_the_track_side():
    # an RTMPose-only observation (score 0.5, no side evidence) keeps the track's side and id
    frames = [[hand(.3)] for _ in range(5)] + [[hand(.3, side="Right", score=.5, origin="hand_detector",
                                                  detail="rtmpose_fitted_3d")] for _ in range(5)]
    out = run(frames, **PRESET)
    assert set(sides(out)) == {"Right"}
    p = [[r["side_probability_right_smoothed"] for r in f if r["observed"]][0] for f in out]
    assert p[-1] == p[4]                                           # P(right) not pulled towards 0.5


def test_track_started_by_a_crop_detection_is_undecided_until_evidence():
    out = run([[hand(.3, side="Left", origin="center_crop_rescue")]], **PRESET)
    assert out[0][0]["side_probability_right_smoothed"] == .5 and out[0][0]["side"] == "unknown"
