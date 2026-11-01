import cv2
import json
import numpy as np
import pytest
from types import SimpleNamespace

from motioniq.lift import EquidistantFisheye, lift_run, solve_hand


@pytest.mark.parametrize("hfovs,existing", [([120., 150.], "json"), ([120., 150.], "npz"),
                                            ([120.1, 120.4], None)])
def test_lift_sweep_rejects_conflicts_before_writing_any_pair(tmp_path, hfovs, existing):
    from motioniq.cli import lift_command

    (tmp_path/"COMPLETE").touch()
    (tmp_path/"manifest.json").write_text(json.dumps({"source": {"width": 160, "height": 90}}))
    (tmp_path/"landmarks.jsonl").write_text('{"frame_index":0,"timestamp_s":0,"hands":[]}\n')
    preserved = tmp_path/f"lift_hfov150.{existing}" if existing else None
    if preserved:
        preserved.write_bytes(b"preserve this existing result")
    with pytest.raises(ValueError, match="never overwritten|duplicate"):
        lift_command(SimpleNamespace(run=str(tmp_path), hfov=hfovs, max_reproj_px=25.))
    assert not (tmp_path/"lift_hfov120.npz").exists()
    assert not (tmp_path/"lift_hfov120.json").exists()
    if preserved:
        assert preserved.read_bytes() == b"preserve this existing result"

W, H = 1920, 1080


def synthetic_hand():
    """Non-planar 21-point hand-like shape in meters, centered near the origin."""
    rng = np.random.default_rng(0)
    base = np.zeros((21, 3))
    for finger in range(5):
        for k in range(4):
            j = 1 + finger*4 + k
            base[j] = [(finger-2)*.018, -(.03 + k*.022), .01*np.sin(finger+k)]
    base += rng.normal(0, .002, base.shape)
    return base - base.mean(axis=0)


def test_projection_round_trip():
    cam = EquidistantFisheye(W, H, 150)
    pts = np.array([[.1, .05, .4], [-.3, .2, .5], [0., 0., 1.]])
    px = cam.project(pts)
    norm, valid = cam.pixels_to_normalized(px)
    assert valid.all()
    np.testing.assert_allclose(norm, pts[:, :2]/pts[:, 2:], rtol=1e-6, atol=1e-9)


@pytest.mark.parametrize("t", [[.05, .12, .35], [-.2, .15, .5], [.25, -.05, .8]])
def test_pnp_recovers_known_pose_including_off_axis(t):
    cam = EquidistantFisheye(W, H, 150)
    world = synthetic_hand()
    R, _ = cv2.Rodrigues(np.array([.3, -.4, .2]))
    pts = world @ R.T + t
    image = cam.project(pts)/[W, H]
    r = solve_hand(cam, image, world)
    assert r["ok"], r["reason"]
    np.testing.assert_allclose(r["t_cam_m"], t, atol=1e-4)
    assert r["reproj_rmse_px"] < 1e-3


def test_wrong_focal_length_scales_depth_not_validated_by_residual():
    true = EquidistantFisheye(W, H, 150)
    world = synthetic_hand()
    image = true.project(world + [0., .1, .4])/[W, H]
    wide = solve_hand(EquidistantFisheye(W, H, 180), image, world)
    narrow = solve_hand(EquidistantFisheye(W, H, 120), image, world)
    assert wide["ok"] and narrow["ok"]
    # Assuming a wider FOV (shorter focal length) places the same pixels closer.
    assert wide["t_cam_m"][2] < .4 < narrow["t_cam_m"][2]


def test_rejects_hands_outside_valid_rays_and_bad_fits():
    cam = EquidistantFisheye(W, H, 150)
    world = synthetic_hand()
    corner = np.tile([[0., 0.]], (21, 1)) + np.linspace(0, .01, 21)[:, None]
    # Near-collinear landmarks (partly beyond the valid ray cone) must be rejected,
    # even though an unchecked PnP fit returned a ~4 px residual here.
    assert solve_hand(cam, corner, world)["reason"] in ("too_few_rays_inside_85deg", "degenerate_2d_configuration")
    image = cam.project(world + [0., 0., .4])/[W, H]
    scrambled = image[::-1]  # landmarks inconsistent with the 3D shape
    r = solve_hand(cam, scrambled, world, max_reproj_px=2.)
    assert not r["ok"]


def test_lift_refuses_existing_pair_before_writing(tmp_path):
    (tmp_path/"COMPLETE").touch()
    summary = tmp_path/"lift_hfov150.json"
    summary.write_bytes(b"keep these bytes\n")
    with pytest.raises(ValueError, match="never overwritten"):
        lift_run(tmp_path, 150)
    assert summary.read_bytes() == b"keep these bytes\n"
    assert not (tmp_path/"lift_hfov150.npz").exists()
