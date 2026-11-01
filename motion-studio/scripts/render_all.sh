#!/usr/bin/env bash
# Render all formats from the same timeline and mux the synthesized score.
set -euo pipefail
cd "$(dirname "$0")/.."
SUB="${SUB:-2}"
python3 scripts/grain.py
python3 scripts/build_data.py
python3 scripts/music.py
for f in 9x16 1x1 16x9; do
  node scripts/render.js video "$f" "build/video_$f.mp4" 60 "$SUB" > "build/render_$f.log" 2>&1 &
done
wait
for f in 9x16 1x1 16x9; do
  ffmpeg -loglevel error -y -i "build/video_$f.mp4" -i build/score.wav -map 0:v -map 1:a \
    -c:v copy -c:a aac -b:a 256k -ar 48000 -shortest -movflags +faststart "out/MOTIONIQ_showreel_$f.mp4"
done
ls -la out/
