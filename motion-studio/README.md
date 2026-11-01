# MOTIONIQ showreel (20 s, 120 BPM)

A 20-second motion-graphics piece for MOTIONIQ, rendered from one timeline in 9:16, 1:1 and 16:9.

| Beat | Time | What happens |
| --- | --- | --- |
| 1 Hook | 0–3 s | "WHICH SECONDS CAN YOU TRUST?" One word per beat, then a zoom through the O of SECONDS |
| 2 Product | 3–7 s | The MOTIONIQ wordmark slams in and flies into the real header. Panels land on 8th notes and the UI plays back |
| 3 Feature | 7–10 s | **Hands in 3D**: the cursor drags to orbit the real 3D canvas |
| 4 Feature | 10–13 s | **Every second, graded**: the cursor scrubs the real timeline, with tags at the lost and reacquired events |
| 5 Feature | 13–16 s | **Jump to the problems**: click "Problems only", then click "Left hand lost". The video seeks to 00:03.600 |
| 6 Proof | 16–20 s | **239 tests passed** (197 pipeline + 42/42 backend), then the logo lockup |

## Files

- `assets/`: real captures and the inventory (`assets/ASSETS.md`). Nothing in the product UI is redrawn.
- `comp/`: the composition (HTML/JS). `window.seek(t)` renders any time deterministically. `comp/timeline.json` is the single source of truth for picture and sound.
- `scripts/capture.js`: Playwright captures of `frontend/prototype/index.html`, including the three real interactions.
- `scripts/music.py`: original score and SFX, synthesized with numpy/scipy from `timeline.json`.
- `scripts/analyze_audio.py`: librosa QA covering tempo, onset-to-grid alignment and cue hits.
- `scripts/render.js`: Playwright frame renderer piped to ffmpeg. Sub-frames are averaged for motion blur.
- `scripts/render_all.sh`: builds everything and muxes the score.
- `out/`: final MP4s and `contact_sheet.png`.

This repo's compliance rules keep media out of git (`*.png`, `*.jpg`, `*.mp4` are ignored, and the pre-commit hook blocks files over 2 MB). Only source is committed. Re-run the capture and render steps to regenerate the screenshots, grain tiles, score and videos.

## Rebuild

```bash
npm i -D playwright                                       # or use a preinstalled Playwright
pip install numpy scipy soundfile librosa matplotlib
node scripts/capture.js && node scripts/brand_rect.js   # re-capture the UI into assets/ui (git-ignored media)
bash scripts/render_all.sh                                # score + three formats (SUB=1 for a fast draft)
```

Stills for review: `node scripts/render.js stills 9x16 build/stills 2.45 6.4 9.0`.

## Honesty notes

- The viewer runs on its built-in **synthetic demo data**, and the film says so on screen.
- The `[METRIC]` slot was blank, and the repo marks accuracy as not measured. The number shown is the README's verification line (1 Nov 2026), which was not re-run here.
- Fonts: headlines use Arial (the deck's font, rendered with Liberation Sans). The wordmark uses the UI's `system-ui` stack, which renders as Inter in this container.
