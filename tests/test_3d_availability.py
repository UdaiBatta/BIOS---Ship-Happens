"""Test 8: an RTMPose-only hand has 2D output, keeps its track, and is never reported as observed 3D."""
import numpy as np

from motioniq.model import Detection
from motioniq.tracking import IdentityTracker


def hand(x, detail=None, score=.95):
    image = np.zeros((21, 3))
    image[:, 0] = x + np.linspace(0, .08, 21)
    image[:, 1] = .5 + np.linspace(0, .12, 21)
    return Detection(image, np.full((21, 3), .01), "Right", score,
                     origin="hand_detector" if detail else "full_frame", origin_detail=detail)


def test_rtmpose_only_hand_is_2d_observed_with_inferred_3d_and_inherited_side():
    t = IdentityTracker(box_link=True, side_hysteresis=.15)
    first = t.update([hand(.3)], 0.)[0]
    second = t.update([hand(.302, detail="rtmpose_fitted_3d", score=.5)], 1/30)[0]
    assert first["landmark_source"] == "mediapipe" and first["world_source"] == "mediapipe_world"
    assert first["provenance"]["world_xyz_m_raw"] == "predicted"
    assert second["track_id"] == first["track_id"] and second["observed"]          # Test 7: same physical track
    assert second["landmark_source"] == "rtmpose" and second["world_source"] == "fitted_from_2d"
    assert second["provenance"]["world_xyz_m_raw"] == "inferred"                    # never "predicted" (observed)
    assert second["side_source"] == "inherited_from_track" and second["side"] == first["side"]
    assert second["image_xyz_raw"] is not None


def test_lost_hand_has_no_3d():
    t = IdentityTracker()
    t.update([hand(.3)], 0.)
    lost = t.update([], 2.)[0]
    assert lost["state"] in ("lost", "retired") and lost["world_xyz_m"] is None and lost["world_source"] is None
