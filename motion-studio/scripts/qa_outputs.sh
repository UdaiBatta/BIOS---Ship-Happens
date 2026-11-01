#!/usr/bin/env bash
# Verify final outputs: streams, duration, size, and sync (white flash frame vs audio drop at 3.0 s).
cd "$(dirname "$0")/.."
for f in 9x16 1x1 16x9; do
  o="out/MOTIONIQ_showreel_$f.mp4"
  echo "== $o ($(du -h "$o" | cut -f1))"
  ffprobe -v error -show_entries stream=codec_type,codec_name,width,height,r_frame_rate,sample_rate,channels -show_entries format=duration -of compact "$o"
  # brightest frame between 2.9 s and 3.2 s should be the drop flash at 3.000 s
  ffmpeg -v error -ss 2.9 -t 0.3 -i "$o" -vf "signalstats,metadata=print:key=lavfi.signalstats.YAVG:file=-" -an -f null - \
    | awk '/pts_time/{split($0,a,"pts_time:"); t=a[2]} /YAVG/{split($0,b,"="); if (b[2]>m){m=b[2]; mt=t}} END{printf "  flash peak at %.3f s (offset from 2.9 s seek)\n", mt+2.9}'
done
