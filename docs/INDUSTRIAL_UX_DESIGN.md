# Industrial UX changes

**Done (tested in Chromium):**
- **Workspaces** (header tabs):
  - Review: video, 3D, timeline, events and frame details.
  - Analysis: timeline, motion signals, events and export, without the video and 3D panels.
  - Diagnostics: everything, with diagnostic lanes on.
- **Video / 3D split:** draggable divider plus Balanced / Video / 3D presets. The video keeps 16:9 and is never stretched.
- **3D controls:** skeleton / mesh / both, wireframe, mesh opacity, Reset view (also double-click), raw / smoothed, approx. camera-space vs hand-relative.
- **Backend bar:** video first, then that video's runs, scan, Upload…, preset, segment, Process, and a debug-labels switch for presentations.
- **Honest labels:**
  - "approx. camera-space (assumed lens)";
  - depth shown as "≈0.4 m est.";
  - "Unknown side" instead of a guess;
  - meshes labelled as joint-skinned (not fitted);
  - lost tracks listed as a note, not as hands.
- **States and errors:**
  - no runs for this video ("Process it");
  - no registered videos ("add files to media/ and scan");
  - unreadable or missing files;
  - server running old code;
  - 3D rejection reasons;
  - "No hands in this frame";
  - no data at this time.

**Not done (time):** follow-selected-hand camera, axes toggle, trajectory toggle beyond the 2 s wrist trails, video search/filter, and a full visual restyle (the teammate's dark theme is kept).
