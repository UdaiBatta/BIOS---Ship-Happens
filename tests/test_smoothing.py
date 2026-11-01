"""Offline smoothing: no lag on fast motion, less jitter when still, per track, raw untouched."""
import numpy as np

from motioniq.smoothing import WORLD_FINGER_BONES, rts_wrist, smooth_samples


def _hand(track, x, y, observed=True):
    image = np.zeros((21, 3))
    image[:, 0], image[:, 1] = x + np.linspace(0, .02, 21), y
    return {"track_id": track, "observed": observed, "image_xyz_raw": image.tolist(), "image_xyz": image.tolist(),
            "world_xyz_m_raw": np.zeros((21, 3)).tolist(), "world_xyz_m": np.zeros((21, 3)).tolist()}


def test_rts_follows_fast_motion_without_lag():
    t = np.arange(30)/30
    path = np.stack([100 + 900*t, np.full(30, 500.)], 1)            # 900 px/s
    assert np.max(np.abs(rts_wrist(t, path) - path)) < 2.


def test_rts_reduces_jitter_on_a_still_wrist():
    rng = np.random.default_rng(0)
    t = np.arange(60)/30
    noisy = np.array([500., 500.]) + rng.normal(0, 4, (60, 2))
    out = rts_wrist(t, noisy)
    jitter = lambda a: np.mean(np.linalg.norm(a[2:] - 2*a[1:-1] + a[:-2], axis=1))
    assert jitter(out) < .5*jitter(noisy)


def test_smoothing_is_per_track_keeps_raw_and_stops_at_gaps():
    rng = np.random.default_rng(1)
    samples = []
    for i in range(40):
        hands = [_hand(1, .3 + rng.normal(0, .003), .5), _hand(2, .7 + rng.normal(0, .003), .5)]
        if 18 <= i < 22:
            hands[0] = {**hands[0], "observed": False, "image_xyz_raw": None}
        samples.append({"timestamp_s": i/30, "hands": hands})
    raw_before = [h["image_xyz_raw"] for s in samples for h in s["hands"]]
    n = smooth_samples(samples, 1920, 1080)
    assert n == 76                                                    # 80 hands minus 4 unobserved
    assert [h["image_xyz_raw"] for s in samples for h in s["hands"]] == raw_before
    xs = {k: [s["hands"][k]["image_xyz"][0][0] for s in samples if s["hands"][k]["observed"]] for k in (0, 1)}
    assert abs(np.mean(xs[0]) - .3) < .01 and abs(np.mean(xs[1]) - .7) < .01   # tracks never mixed


def test_rotating_hand_keeps_3d_bone_lengths_without_copying_one_frame_glitch():
    base = np.array([
        [0, 0, 0], [-.02, -.015, 0], [-.035, -.02, 0], [-.045, -.03, 0], [-.055, -.035, 0],
        [-.018, -.04, 0], [-.025, -.06, 0], [-.03, -.08, 0], [-.035, -.095, 0],
        [0, -.045, 0], [0, -.07, 0], [0, -.095, 0], [0, -.11, 0],
        [.018, -.04, 0], [.025, -.06, 0], [.03, -.08, 0], [.035, -.095, 0],
        [.034, -.032, 0], [.043, -.048, 0], [.048, -.064, 0], [.052, -.076, 0],
    ])
    samples = []
    for i in range(12):
        angle = i*.45
        rotation = np.array([[np.cos(angle), -np.sin(angle), 0],
                             [np.sin(angle), np.cos(angle), 0], [0, 0, 1]])
        world = base @ rotation.T
        if i == 6:
            world[8] = world[7]  # A collapsed raw detection must remain identifiable.
        hand = _hand(1, .5, .5)
        hand['world_xyz_m_raw'] = world.tolist()
        hand['world_xyz_m'] = world.tolist()
        samples.append({'timestamp_s': i/30, 'hands': [hand]})
    raw_before = [sample['hands'][0]['world_xyz_m_raw'] for sample in samples]
    smooth_samples(samples, 1920, 1080)
    assert [sample['hands'][0]['world_xyz_m_raw'] for sample in samples] == raw_before
    for i, sample in enumerate(samples):
        hand = sample['hands'][0]
        raw = np.asarray(hand['world_xyz_m_raw'])
        smooth = np.asarray(hand['world_xyz_m'])
        for parent, child in WORLD_FINGER_BONES:
            if (parent, child) == (7, 8) and i >= 6:
                continue
            np.testing.assert_allclose(np.linalg.norm(smooth[child] - smooth[parent]),
                                       np.linalg.norm(raw[child] - raw[parent]), atol=1e-12)
    raw_glitch = np.asarray(samples[6]['hands'][0]['world_xyz_m_raw'])
    smooth_glitch = np.asarray(samples[6]['hands'][0]['world_xyz_m'])
    assert np.linalg.norm(raw_glitch[8] - raw_glitch[7]) == 0
    assert np.linalg.norm(smooth_glitch[8] - smooth_glitch[7]) > .01
    # The filter still changes directions; this is not simply returning raw landmarks.
    assert not np.allclose(samples[5]['hands'][0]['world_xyz_m'], samples[5]['hands'][0]['world_xyz_m_raw'])
    raw = np.asarray(samples[5]['hands'][0]['world_xyz_m_raw'])
    smooth = np.asarray(samples[5]['hands'][0]['world_xyz_m'])
    raw_direction = raw[6] - raw[5]
    smooth_direction = smooth[6] - smooth[5]
    assert np.dot(raw_direction, smooth_direction)/(np.linalg.norm(raw_direction)*np.linalg.norm(smooth_direction)) > .999999


def test_finger_direction_reduces_single_frame_spike_but_follows_sustained_bend():
    def run(turned):
        samples = []
        for i in range(12):
            world = np.zeros((21, 3))
            world[5:9] = [[.01, -.01, 0], [.01, -.03, 0], [.01, -.05, 0], [.01, -.07, 0]]
            if turned(i):
                world[8] = [.03, -.05, 0]
            hand = _hand(1, .5, .5)
            hand['world_xyz_m_raw'] = world.tolist()
            samples.append({'timestamp_s': i/30, 'hands': [hand]})
        smooth_samples(samples, 1920, 1080)
        return [np.asarray(s['hands'][0]['world_xyz_m']) for s in samples]

    spike = run(lambda i: i == 5)
    direction = spike[5][8] - spike[5][7]
    assert np.dot(direction, [0, -1, 0])/np.linalg.norm(direction) > .7  # about 45 degrees from steady finger
    bend = run(lambda i: i >= 5)
    direction = bend[7][8] - bend[7][7]
    assert np.dot(direction, [1, 0, 0])/np.linalg.norm(direction) > .999


def test_variable_frame_rate_rotation_has_no_direction_lag():
    samples = []
    for time in (0., .008, .108):
        angle = 13.5*time
        rotation = np.array([[np.cos(angle), -np.sin(angle), 0],
                             [np.sin(angle), np.cos(angle), 0], [0, 0, 1]])
        world = np.zeros((21, 3))
        world[5:9] = np.array([[0, -.02, 0], [0, -.04, 0], [0, -.06, 0], [0, -.08, 0]]) @ rotation.T
        hand = _hand(1, .5, .5)
        hand['world_xyz_m_raw'] = world.tolist()
        samples.append({'timestamp_s': time, 'hands': [hand]})
    smooth_samples(samples, 1920, 1080)
    raw = np.asarray(samples[1]['hands'][0]['world_xyz_m_raw'])
    smooth = np.asarray(samples[1]['hands'][0]['world_xyz_m'])
    a, b = raw[6] - raw[5], smooth[6] - smooth[5]
    assert np.dot(a, b)/(np.linalg.norm(a)*np.linalg.norm(b)) > .999999
