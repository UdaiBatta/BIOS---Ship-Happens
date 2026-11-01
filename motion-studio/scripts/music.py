"""Original 20 s soundtrack for the MOTIONIQ showreel, synthesized from scratch at 120 BPM.

All cue times come from comp/timeline.json (the same file the visuals use), so UI clicks,
whooshes and impacts land on the frames they belong to. Output: build/score.wav (48 kHz, 24-bit).
"""
import json
import pathlib

import numpy as np
import soundfile as sf
from scipy import signal

ROOT = pathlib.Path(__file__).resolve().parent.parent
TL = json.loads((ROOT / 'comp/timeline.json').read_text())
SR = 48000
DUR = TL['duration']
N = int(DUR * SR)
BEAT = 60.0 / TL['bpm']            # 0.5 s
rng = np.random.default_rng(120)

bus = {k: np.zeros((2, N + SR * 3)) for k in ('drums', 'music', 'sfx', 'verb')}


# ------------------------------------------------------------------ utils
def tt(d):
    return np.arange(int(d * SR)) / SR


def place(name, x, t0, gain=1.0, pan=0.0, verb=0.0):
    """Mix mono/stereo buffer x into a bus at time t0 with equal-power pan and a reverb send."""
    i = int(round(t0 * SR))
    if i < 0:
        x = x[..., -i:] if x.ndim == 1 else x[:, -i:]
        i = 0
    if x.ndim == 1:
        a = (pan + 1) * np.pi / 4
        x = np.vstack([x * np.cos(a), x * np.sin(a)]) * np.sqrt(2)
    n = min(x.shape[1], bus[name].shape[1] - i)
    if n <= 0:
        return
    bus[name][:, i:i + n] += x[:, :n] * gain
    if verb:
        bus['verb'][:, i:i + n] += x[:, :n] * gain * verb


def sos(kind, f, order=2):
    return signal.butter(order, f, btype=kind, fs=SR, output='sos')


def filt(x, kind, f, order=2):
    return signal.sosfilt(sos(kind, f, order), x, axis=-1)


def sweep(x, kind, f_of_t, block=256, order=2):
    """Time-varying Butterworth filter, coefficients updated every block (state carried)."""
    y = np.zeros_like(x)
    zi = None
    for s in range(0, x.shape[-1], block):
        tm = s / SR
        f = float(np.clip(f_of_t(tm), 30, SR * 0.45))
        if kind == 'band':
            f = [max(30, f * 0.7), min(SR * 0.45, f * 1.4)]
        so = sos(kind, f, order)
        if zi is None:
            zi = np.zeros((so.shape[0], 2))
        y[s:s + block], zi = signal.sosfilt(so, x[s:s + block], zi=zi)
    return y


def env_adsr(n, a=0.005, d=0.1, s=0.6, r=0.05):
    e = np.ones(n) * s
    na, nd, nr = int(a * SR), int(d * SR), int(r * SR)
    na = max(1, min(na, n)); e[:na] = np.linspace(0, 1, na)
    nd2 = max(0, min(nd, n - na)); e[na:na + nd2] = np.linspace(1, s, nd2) if nd2 else e[na:na + nd2]
    nr = min(nr, n); e[n - nr:] *= np.linspace(1, 0, nr)
    return e


def saw(f, d, phase=0.0):
    t = tt(d)
    return 2 * ((f * t + phase) % 1.0) - 1


def midi(m):
    return 440.0 * 2 ** ((m - 69) / 12)


# ------------------------------------------------------------------ drums
def kick(big=False):
    t = tt(0.55 if big else 0.4)
    f = 46 + (150 if big else 115) * np.exp(-t / 0.032)
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / (0.32 if big else 0.21))
    click = filt(rng.normal(0, 1, len(t)), 'high', 2500) * np.exp(-t / 0.0025) * 0.5
    return np.tanh(1.6 * (x + click)) * 0.95


def clap():
    t = tt(0.35)
    n = rng.normal(0, 1, len(t))
    e = np.zeros(len(t))
    for k, o in enumerate((0.0, 0.011, 0.023)):
        i = int(o * SR); e[i:] += np.exp(-(t[i:] - o) / 0.006) * (0.8 if k < 2 else 1)
    i = int(0.023 * SR); e[i:] += 0.55 * np.exp(-(t[i:] - 0.023) / 0.09)
    x = filt(n * e, 'band', [900, 4200])
    l, r = x, np.roll(x, int(0.006 * SR))
    return np.vstack([l, r]) * 0.9


def hat(open_=False):
    t = tt(0.3 if open_ else 0.08)
    x = filt(rng.normal(0, 1, len(t)), 'high', 7500) * np.exp(-t / (0.12 if open_ else 0.018))
    return x * 0.5


def snare(v=1.0):
    t = tt(0.25)
    tone = np.sin(2 * np.pi * 190 * t) * np.exp(-t / 0.06)
    nz = filt(rng.normal(0, 1, len(t)), 'band', [1200, 7000]) * np.exp(-t / 0.1)
    return (0.5 * tone + 0.8 * nz) * v


# ------------------------------------------------------------------ tonal
def supersaw(freqs, d, cutoff, detune=(-15, -8, -3, 0, 3, 8, 15)):
    n = int(d * SR)
    out = np.zeros((2, n))
    for f in freqs:
        for k, c in enumerate(detune):
            ff = f * 2 ** (c / 1200)
            v = saw(ff, d, rng.random())
            p = (k / (len(detune) - 1)) * 2 - 1
            a = (p * 0.8 + 1) * np.pi / 4
            out[0] += v * np.cos(a); out[1] += v * np.sin(a)
    out /= (len(freqs) * len(detune)) ** 0.5 * 2.2
    if callable(cutoff):
        out = np.vstack([sweep(out[0], 'low', cutoff), sweep(out[1], 'low', cutoff)])
    else:
        out = filt(out, 'low', cutoff)
    return out


def bass(f, d, cutoff=520):
    t = tt(d)
    x = 0.7 * filt(saw(f, d), 'low', cutoff) + 0.6 * np.sin(2 * np.pi * f * t)
    return np.tanh(1.4 * x) * env_adsr(len(t), 0.004, 0.08, 0.75, 0.03)


def pluck(f, d=0.32):
    t = tt(d)
    idx = 2.6 * np.exp(-t / 0.05)
    x = np.sin(2 * np.pi * f * t + idx * np.sin(2 * np.pi * 2 * f * t)) * np.exp(-t / 0.13)
    return x * env_adsr(len(t), 0.002, 0.05, 1.0, 0.02)


def bell(f, d=1.4):
    t = tt(d)
    idx = 3.0 * np.exp(-t / 0.3)
    return np.sin(2 * np.pi * f * t + idx * np.sin(2 * np.pi * 3.5 * f * t)) * np.exp(-t / 0.45)


# ------------------------------------------------------------------ sfx
def impact(big=True):
    t = tt(1.6 if big else 0.8)
    f = 30 + 40 * np.exp(-t / 0.12)
    sub = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / (0.7 if big else 0.3))
    nz = filt(rng.normal(0, 1, len(t)), 'low', 2200) * np.exp(-t / (0.22 if big else 0.1))
    crack = filt(rng.normal(0, 1, len(t)), 'high', 3000) * np.exp(-t / 0.02)
    return np.tanh(1.3 * (0.9 * sub + 0.45 * nz + 0.25 * crack))


def whoosh(d=0.45, up=True):
    t = tt(d)
    nz = rng.normal(0, 1, len(t))
    u = t / d
    f = (lambda tm: 300 * (30 ** (tm / d))) if up else (lambda tm: 6000 * (0.08 ** (tm / d)))
    x = sweep(nz, 'band', f)
    amp = np.sin(np.pi * np.clip(u, 0, 1)) ** 2 if not up else (u ** 2.2) * (1 - np.clip((u - 0.93) / 0.07, 0, 1))
    x = x * amp
    pan = np.linspace(-0.8, 0.8, len(t))
    a = (pan + 1) * np.pi / 4
    return np.vstack([x * np.cos(a), x * np.sin(a)]) * 0.9


def riser(d):
    t = tt(d)
    nz = sweep(rng.normal(0, 1, len(t)), 'band', lambda tm: 250 * (40 ** (tm / d)))
    ph = 2 * np.pi * np.cumsum(180 * (8 ** (t / d))) / SR
    tone = np.sin(ph) * 0.25 + np.sin(ph * 1.5) * 0.12
    amp = (t / d) ** 2.5
    return (nz * 0.8 + tone) * amp


def rev_cymbal(d=0.6):
    t = tt(d)
    x = filt(rng.normal(0, 1, len(t)), 'high', 4500) * np.exp(-(d - t) / 0.18)
    return np.vstack([x, np.roll(x, 90)]) * 0.5


def crash():
    t = tt(1.4)
    x = filt(rng.normal(0, 1, len(t)), 'high', 3800) * np.exp(-t / 0.45)
    return np.vstack([x, np.roll(x, 140)]) * 0.45


def click(kind='down'):
    t = tt(0.05)
    f = {'down': 2100, 'up': 2900, 'tick': 3600, 'pop': 1400}[kind]
    x = np.sin(2 * np.pi * f * t) * np.exp(-t / 0.006)
    x += filt(rng.normal(0, 1, len(t)), 'high', 5000) * np.exp(-t / 0.0015) * 0.6
    if kind == 'down':
        x += np.sin(2 * np.pi * 180 * t) * np.exp(-t / 0.015) * 0.7
    return x


def thock():
    t = tt(0.16)
    f = 95 + 120 * np.exp(-t / 0.02)
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.05)
    return x + 0.6 * click('tick')[:len(t)] if len(t) <= len(click('tick')) else x + np.pad(0.6 * click('tick'), (0, len(t) - len(click('tick'))))


def blip(f, d=0.06):
    t = tt(d)
    return np.sin(2 * np.pi * f * t) * np.exp(-t / 0.018)


# ------------------------------------------------------------------ harmony
CH = {  # (bass midi, chord midi notes)
    'Am': (45, [57, 60, 64, 69]), 'F': (41, [53, 57, 60, 65]), 'C': (48, [55, 60, 64, 67]),
    'G': (43, [55, 59, 62, 67]), 'Cadd9': (36, [55, 60, 64, 67, 74]),
}
PLAN = [(0.0, 3.0, 'Am'), (3.0, 5.0, 'F'), (5.0, 7.0, 'C'), (7.0, 10.0, 'G'), (10.0, 13.0, 'Am'),
        (13.0, 16.0, 'F'), (16.0, 18.0, 'G'), (18.0, 20.0, 'Cadd9')]


def chord_at(t):
    for a, b, c in PLAN:
        if a <= t < b:
            return c
    return PLAN[-1][2]


# ------------------------------------------------------------------ arrangement
words = [w[1] for w in TL['words']]
drop, lock, lockup = TL['drop'], TL['metric']['lock'], TL['metric']['lockup']

# HOOK: each word lands with kick + bass stab + slam
for i, w in enumerate(words):
    big = i == len(words) - 1
    place('drums', kick(big), w, 1.0)
    place('sfx', impact(False) if not big else impact(True), w, 0.55 if not big else 0.8, verb=0.25)
    place('music', bass(midi(CH['Am'][0]), 0.22), w + 0.0, 0.7)
    place('sfx', filt(rng.normal(0, 1, int(0.12 * SR)), 'band', [600, 5000]) * np.exp(-tt(0.12) / 0.03), w, 0.35, pan=(-0.4 if i % 2 else 0.4))
# hook pad with opening filter
pad = supersaw([midi(m) for m in CH['Am'][1]], 3.1, lambda tm: 250 + 2600 * (tm / 3.0) ** 2)
place('music', pad * np.linspace(0.2, 1, pad.shape[1]), 0.0, 0.55, verb=0.3)
# tension: riser + snare roll + reverse cymbal into the drop
place('sfx', riser(1.0), 2.0, 0.55)
for k, (a, b, step) in enumerate(((2.0, 2.5, 0.25), (2.5, 2.75, 0.125), (2.75, 3.0, 0.0625))):
    for tr in np.arange(a, b - 1e-6, step):
        place('drums', snare(0.35 + 0.65 * (tr - 2.0)), tr, 0.55)
place('sfx', rev_cymbal(0.7), drop - 0.7, 0.7)
place('sfx', whoosh(0.5, up=True), drop - 0.5, 0.7)

# MAIN GROOVE 3.0 - 16.0
for b in np.arange(drop, 16.0 - 1e-6, BEAT):
    place('drums', kick(b == drop), b, 1.0)
for b in np.arange(drop + BEAT, 16.0 - 1e-6, 2 * BEAT):
    place('drums', clap(), b, 0.55, verb=0.18)
for s in np.arange(drop, 16.0 - 1e-6, BEAT / 4):
    beat_pos = round((s - drop) / (BEAT / 4)) % 4
    if beat_pos == 2:
        place('drums', hat(True), s, 0.32, pan=0.25)
    else:
        place('drums', hat(False), s, 0.22 if beat_pos else 0.12, pan=-0.2)
# offbeat bass, octave pops in the feature section
for s in np.arange(drop + BEAT / 2, 16.0 - 1e-6, BEAT):
    root = CH[chord_at(s)][0]
    octv = 12 if (s >= 10.0 and int((s - drop) / BEAT) % 4 == 3) else 0
    place('music', bass(midi(root + octv), 0.2, 700 if s >= 7 else 520), s, 0.75)
# chords (sidechained later), brighter from feature 1
for a, b, c in PLAN[1:6]:
    cut = 2200 if a < 7 else 4200
    place('music', supersaw([midi(m) for m in CH[c][1]], b - a + 0.05, cut), a, 0.5, verb=0.22)
# arp: 16th FM plucks through the features, with ping-pong delay
pat = [0, 2, 3, 1, 3, 2, 4, 2]
for k, s in enumerate(np.arange(7.0, 16.0 - 1e-6, BEAT / 4)):
    notes = CH[chord_at(s)][1] + [CH[chord_at(s)][1][0] + 12]
    f = midi(notes[pat[k % 8] % len(notes)] + 12)
    v = 0.22 + 0.06 * (k % 4 == 0)
    place('music', pluck(f), s, v, pan=(-0.35 if k % 2 else 0.35), verb=0.15)
    place('music', pluck(f), s + 0.375, v * 0.35, pan=(0.6 if k % 2 else -0.6))
# section fills + transitions
for a in (6.5,):
    for i, tr in enumerate(np.arange(a, a + 0.5 - 1e-6, 0.0625)):
        place('drums', snare(0.3 + 0.08 * i), tr, 0.5)
for a in (9.75, 12.75):
    for i, tr in enumerate(np.arange(a, a + 0.25 - 1e-6, 0.0625)):
        place('drums', snare(0.4 + 0.12 * i), tr, 0.45)
for edge in (7.0, 10.0, 13.0):
    place('sfx', whoosh(0.45, up=True), edge - 0.45, 0.6)
    place('sfx', crash(), edge, 0.5, verb=0.3)
    place('sfx', impact(False), edge, 0.45)

# PRODUCT: wordmark slam, morph whoosh, panel landings on 8ths
place('sfx', impact(True), drop, 0.9, verb=0.35)
place('sfx', crash(), drop, 0.6, verb=0.4)
m0, m1 = TL['wordmark']['morph']
place('sfx', whoosh(m1 - m0 + 0.1, up=True), m0 - 0.1, 0.4)
for name, land in TL['panels']:
    place('sfx', whoosh(0.28, up=True), land - 0.28, 0.22)
    place('sfx', thock(), land, 0.7, pan=rng.uniform(-0.4, 0.4))
for _, t0 in TL['productCaptions']:
    place('sfx', click('pop'), t0, 0.35)
place('sfx', whoosh(0.3, up=True), TL['zoomToF1'][0], 0.6)

# FEATURE 1: press, drag, release, chips
f1 = TL['f1']
place('sfx', click('down'), f1['press'], 0.9)
drag = sweep(rng.normal(0, 1, int((f1['release'] - f1['press']) * SR)), 'band', lambda tm: 400 + 900 * np.sin(np.pi * tm / 1.75))
place('sfx', drag * np.sin(np.pi * np.linspace(0, 1, len(drag))) * 0.08, f1['press'], 1.0)
place('sfx', click('up'), f1['release'], 0.8)
for t0 in (7.75, 8.0):
    place('sfx', blip(1318.5), t0, 0.25)
for t0 in f1['chips']:
    place('sfx', click('pop'), t0, 0.5)

# FEATURE 2: scrub; tags pop as the playhead crosses real events
f2 = TL['f2']
place('sfx', click('down'), f2['press'], 0.9)
place('sfx', click('up'), f2['release'], 0.8)


def scrub_u(target, T0=1.6, T1=6.4):
    lo, hi = 0.0, 1.0
    for _ in range(50):
        m = (lo + hi) / 2
        e = 2 * m * m if m < 0.5 else 1 - (-2 * m + 2) ** 2 / 2
        if T0 + (T1 - T0) * e < target:
            lo = m
        else:
            hi = m
    return lo


for s_evt, f in ((3.2, 987.8), (3.6, 1318.5), (5.0, 1760.0)):
    tm = f2['press'] + scrub_u(s_evt) * (f2['release'] - f2['press'])
    place('sfx', blip(f), tm, 0.3)
# scrub texture: ticks every 16th while dragging
for tr in np.arange(f2['press'], f2['release'], BEAT / 4):
    place('sfx', click('tick'), tr, 0.12, pan=0.3)

# FEATURE 3: filter click, event click, alert, push, collapse
f3 = TL['f3']
place('sfx', click('down'), f3['clickFilter'], 0.9)
place('sfx', click('down'), f3['clickEvent'], 1.0)
place('sfx', bell(880.0, 0.8) * 0.5 + bell(1318.5, 0.8) * 0.3, f3['clickEvent'] + 0.125, 0.45, verb=0.3)
place('sfx', riser(TL['f3']['push'][1] - TL['f3']['push'][0] + 0.25), TL['f3']['push'][0], 0.35)
place('sfx', whoosh(0.3, up=True), TL['f3']['collapse'][0] - 0.05, 0.6)
for i, tr in enumerate(np.arange(15.5, 16.0 - 1e-6, 0.0625)):
    place('drums', snare(0.3 + 0.09 * i), tr, 0.5)

# PROOF 16 - 18: half-time, counter ticks, lock, build to the logo
place('drums', kick(True), 16.0, 1.0)
place('sfx', impact(True), 16.0, 0.6, verb=0.3)
place('music', supersaw([midi(m) for m in CH['G'][1]], 2.05, lambda tm: 900 + 3500 * (tm / 2.0) ** 2), 16.0, 0.45, verb=0.35)
place('music', bass(midi(CH['G'][0]), 1.9, 400), 16.0, 0.7)
for k, tr in enumerate(np.arange(16.0, lock - 1e-6, BEAT / 8)):
    place('sfx', blip(midi(84 + (k % 8) + (k // 8) * 2), 0.04), tr, 0.18 + 0.01 * k, pan=(-0.3 if k % 2 else 0.3))
place('drums', kick(), lock, 0.95)
place('sfx', bell(1046.5, 1.4) * 0.6 + bell(1567.98, 1.4) * 0.35, lock, 0.6, verb=0.4)
place('sfx', impact(False), lock, 0.5)
for tr in np.arange(lock + BEAT, lockup - 1e-6, BEAT):
    place('drums', kick(), tr, 0.8)
place('drums', clap(), lock + BEAT, 0.45, verb=0.2)
place('sfx', riser(1.0), lock, 0.5)
for i, tr in enumerate(np.arange(17.5, 18.0 - 1e-6, 0.0625)):
    place('drums', snare(0.35 + 0.08 * i), tr, 0.5)
place('sfx', whoosh(0.3, up=True), TL['metric']['collapse'][0] - 0.05, 0.6)
place('sfx', rev_cymbal(0.6), lockup - 0.6, 0.6)

# FINAL: logo lands
place('drums', kick(True), lockup, 1.0)
place('sfx', impact(True), lockup, 1.0, verb=0.45)
place('sfx', crash(), lockup, 0.7, verb=0.5)
place('music', supersaw([midi(m) for m in CH['Cadd9'][1]], 2.2, lambda tm: 4500 * np.exp(-tm / 1.2) + 500), lockup, 0.65, verb=0.55)
place('music', bass(midi(CH['Cadd9'][0]), 1.8, 300), lockup, 0.8)
for k, n in enumerate([72, 76, 79, 84]):
    place('music', pluck(midi(n), 0.6), lockup + 0.25 + k * 0.125, 0.25, pan=(-0.4 + 0.27 * k), verb=0.5)

# ------------------------------------------------------------------ sidechain + mix
kicks = sorted(set([*words, *np.arange(drop, 16.0 - 1e-6, BEAT), 16.0, lock, *np.arange(lock + BEAT, lockup, BEAT), lockup]))
tl = np.arange(bus['music'].shape[1]) / SR
duck = np.ones_like(tl)
for k in kicks:
    i = int(k * SR)
    seg = tl[i:i + int(0.4 * SR)] - k
    duck[i:i + len(seg)] = np.minimum(duck[i:i + len(seg)], 1 - 0.68 * np.exp(-seg / 0.11) * np.clip(seg / 0.004, 0, 1) - 0.0)
bus['music'] *= duck

# reverb: decorrelated exponentially decaying noise, darkening over time
ir_t = tt(2.2)
ir = np.vstack([rng.normal(0, 1, len(ir_t)), rng.normal(0, 1, len(ir_t))]) * np.exp(-ir_t / 0.42)
ir = np.vstack([sweep(ir[0], 'low', lambda tm: 9000 * np.exp(-tm / 0.6) + 600), sweep(ir[1], 'low', lambda tm: 9000 * np.exp(-tm / 0.6) + 600)])
ir /= np.sqrt((ir ** 2).sum(axis=1, keepdims=True))
wet = np.vstack([signal.fftconvolve(bus['verb'][0], ir[0])[:bus['verb'].shape[1]],
                 signal.fftconvolve(bus['verb'][1], ir[1])[:bus['verb'].shape[1]]])
wet = filt(wet, 'high', 250)

mix = 0.95 * bus['drums'] + 0.85 * bus['music'] + 0.9 * bus['sfx'] + 0.55 * wet
mix = filt(mix, 'high', 28)
mix = mix[:, :N]

# dynamics automation: quieter hook, a 1/16-note hole before each drop, proof section breathes in
tA = np.arange(N) / SR
auto = np.ones(N)
auto[tA < drop] = 0.62 + 0.12 * (tA[tA < drop] / drop)
for d0 in (drop, 16.0, lockup):
    hole = (tA >= d0 - 0.0625) & (tA < d0)
    auto[hole] = 0.02
    ramp = (tA >= d0 - 0.0625 - 0.01) & (tA < d0 - 0.0625)
    auto[ramp] = np.linspace(auto[ramp][0] if ramp.any() else 1, 0.02, ramp.sum())
seg = (tA >= 16.0) & (tA < lockup - 0.0625)
auto[seg] *= 0.82 + 0.12 * (tA[seg] - 16.0) / 2.0
auto = signal.lfilter([1 - 0.995], [1, -0.995], auto)   # ~4 ms smoothing, no clicks
mix *= auto

# glue compressor (feed-forward, RMS detector)
det = np.sqrt(signal.lfilter([1 - 0.995], [1, -0.995], (mix ** 2).mean(axis=0)) + 1e-12)
thr = 10 ** (-11 / 20)
gain_db = np.where(det > thr, (20 * np.log10(thr) - 20 * np.log10(det)) * (1 - 1 / 2.2), 0.0)
gain = 10 ** (signal.lfilter([1 - 0.999], [1, -0.999], gain_db) / 20)
mix = mix * gain
# loudness target then soft clip and peak ceiling
rms = np.sqrt((mix ** 2).mean())
mix *= 10 ** (-14.5 / 20) / rms
mix = np.tanh(mix * 1.05) / np.tanh(1.05)
mix *= 10 ** (-1.0 / 20) / np.abs(mix).max()
# tail fade with the picture
fade0, fade1 = TL['metric']['fadeOut']
fl = int((DUR - fade0) * SR)
mix[:, -fl:] *= np.linspace(1, 0, fl) ** 1.5
mix[:, :int(0.004 * SR)] *= np.linspace(0, 1, int(0.004 * SR))

out = ROOT / 'build/score.wav'
sf.write(out, mix.T, SR, subtype='PCM_24')
print(f'wrote {out}  peak {20*np.log10(np.abs(mix).max()):.2f} dBFS  rms {20*np.log10(np.sqrt((mix**2).mean())):.2f} dBFS')
