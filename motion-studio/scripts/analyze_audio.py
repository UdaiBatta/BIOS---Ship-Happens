"""Audio QA with librosa: tempo, beat-grid alignment of onsets, cue hits, spectrogram."""
import json, pathlib, sys
import numpy as np, librosa, librosa.display
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT = pathlib.Path(__file__).resolve().parent.parent
TL = json.loads((ROOT / 'comp/timeline.json').read_text())
y, sr = librosa.load(ROOT / 'build/score.wav', sr=None, mono=True)
tempo, beats = librosa.beat.beat_track(y=y, sr=sr, start_bpm=120, units='time')
on = librosa.onset.onset_detect(y=y, sr=sr, units='time', backtrack=False)
grid = 0.125  # 16th notes at 120 BPM
off = np.abs(on / grid - np.round(on / grid)) * grid * 1000
print(f'duration {len(y)/sr:.2f}s  tempo {float(np.atleast_1d(tempo)[0]):.1f} BPM  beats {len(beats)}')
print(f'onsets {len(on)}; within 15 ms of the 16th grid: {np.mean(off < 15)*100:.0f}%  median offset {np.median(off):.1f} ms')
cues = [w[1] for w in TL['words']] + [TL['drop']] + [p[1] for p in TL['panels']] + [TL['f1']['press'], TL['f1']['release'], TL['f2']['press'], TL['f2']['release'], TL['f3']['clickFilter'], TL['f3']['clickEvent'], 7.0, 10.0, 13.0, 16.0, TL['metric']['lock'], TL['metric']['lockup']]
hits = [(c, np.min(np.abs(on - c)) * 1000) for c in cues]
print('cue -> nearest onset (ms):', ', '.join(f'{c:.2f}:{d:.0f}' for c, d in hits))
print(f'cues on the 8th-note grid: {sum(abs(c/0.25 - round(c/0.25)) < 1e-6 for c in cues)}/{len(cues)}; cues with an onset within 30 ms: {sum(d < 30 for _, d in hits)}/{len(cues)}')
S = librosa.amplitude_to_db(np.abs(librosa.stft(y, n_fft=2048, hop_length=256)), ref=np.max)
fig, ax = plt.subplots(2, 1, figsize=(18, 7), sharex=True, gridspec_kw={'height_ratios': [1, 2.2]})
t = np.arange(len(y)) / sr
ax[0].plot(t[::20], y[::20], lw=0.4, color='#3987e5'); ax[0].set_ylabel('wave')
librosa.display.specshow(S, sr=sr, hop_length=256, x_axis='time', y_axis='log', ax=ax[1], cmap='magma')
for s in TL['sections']:
    for a in ax: a.axvline(s['t0'], color='#fab219', lw=1)
    ax[0].text(s['t0'] + 0.05, 0.9, s['id'], color='#d95926', fontsize=10)
for c in cues: ax[1].axvline(c, color='white', lw=0.4, alpha=0.5)
plt.tight_layout(); plt.savefig(sys.argv[1], dpi=80)
