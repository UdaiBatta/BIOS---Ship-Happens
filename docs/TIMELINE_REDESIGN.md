# Timeline redesign

The timeline is still drawn on a canvas from compact state intervals (runs), so long videos create no DOM per frame. It is drawn once per presented video frame.

**Layers**
- **A. Primary lanes:** Left hand, Right hand and (new) **Unknown side**, plus Other people when present. States: observed (side colour), reacquired (light tick at the start), predicted (muted grey-blue, 2D only), lost (dark neutral: the track is kept but not detected) and no track (background). *Bug fixed:* hands with an unknown side used to show as "not tracked" in both side lanes.
- **B. Events strip:** markers for tracking failure ▼, reacquisition ◆, hand appeared, side unknown, 3D unavailable, and the backend's candidate motion events (hold, movement, long gap). Click to seek and inspect.
- **C. Diagnostics** (collapsed by default; on in the Diagnostics workspace): low blur, 3D valid and mesh lanes, plus the signal charts.

**Interaction**
- **Pointer:** click a lane to seek and open the inspection panel (time, video/run, frame, track, side and its source, state, detection path, landmark model, 3D method, why missing, Play segment, Zoom to segment). Drag to scrub (at most one seek per animation frame). Wheel zooms around the cursor; Shift+wheel or dragging the time axis pans; double-click fits.
- **Hover:** segment start, end, duration, track, detection path and 3D.
- **Buttons:** − / + / Fit, ◀ failure ▶, ◀ reacq. ▶.
- **Keys:**
  - Space: play/pause.
  - ←/→: one frame (when paused); Shift+←/→: 1 s.
  - + / − / 0: zoom in, zoom out, fit.
  - F / Shift+F: next / previous failure; R / Shift+R: next / previous reacquisition.
  - Esc: close the inspection panel.
  - Keys are ignored while typing in a form.
- **While playing zoomed,** the view follows the playhead.

**Accuracy:**
- positions come from the run's own frame timestamps (variable frame rate is respected; no `frame/30`);
- the percentages come from frame-level lane states;
- lost and "no track" are drawn differently;
- the reason a hand is missing is shown only where the tracker recorded one (inferred).

**Verified in Chromium on real backend runs:**
- click at mid-width seeks to 65.02 s (centre 65.00 s);
- zoom to 63.8–66.3 s, then fit;
- F lands on the first failure (62.35 s for an event at 62.333 s);
- R lands on the next reacquisition;
- the scrub sequence 62 → 64 → 66 s;
- Esc closes the panel;
- the diagnostics toggle shows the signals panel;
- no page errors.
