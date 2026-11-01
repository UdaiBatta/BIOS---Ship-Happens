// Captures every real UI asset used in the film from the MOTIONIQ viewer prototype.
// Nothing here is redrawn: every pixel comes from Playwright screenshots of
// frontend/prototype/index.html (offline page, synthetic demo data).
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const URL = 'file://' + require('path').resolve(__dirname, '../../frontend/prototype/index.html');
const OUT = path.resolve(__dirname, '../assets/ui');
const DPR = 2;
const manifest = { dpr: DPR, layouts: {}, sequences: {} };

const mk = (d) => fs.mkdirSync(path.join(OUT, d), { recursive: true });
const rect = async (p, sel) => {
  const b = await p.locator(sel).first().boundingBox();
  return { x: b.x, y: b.y, w: b.width, h: b.height };
};
async function open(b, w, h) {
  const p = await b.newPage({ viewport: { width: w, height: h }, deviceScaleFactor: DPR });
  await p.goto(URL);
  await p.waitForTimeout(900);
  return p;
}
const shotEl = (p, sel, file, type = 'png') =>
  p.locator(sel).first().screenshot({ path: path.join(OUT, file), type, ...(type === 'jpeg' ? { quality: 93 } : {}) });
const shotClip = (p, r, file, type = 'jpeg') =>
  p.screenshot({ path: path.join(OUT, file), clip: { x: r.x, y: r.y, width: r.w, height: r.h }, type, ...(type === 'jpeg' ? { quality: 93 } : {}) });

const PANELS = { header: 'header.top', controls: '.controls', video: '#p-video', three: '#p-three',
  lanes: '#p-lanes', inspect: '#p-inspect', events: '#p-events' };

(async () => {
  const b = await chromium.launch();

  // ---------- 1. Static panels + living playback for both layouts ----------
  for (const [name, vw, vh] of [['L', 1600, 1320], ['P', 1080, 1740]]) {
    const p = await open(b, vw, vh);
    mk(`${name}`); mk(`${name}/live`);
    const page = await p.evaluate(() => ({ w: document.documentElement.scrollWidth, h: document.documentElement.scrollHeight }));
    const L = { page, panels: {} };
    await p.screenshot({ path: path.join(OUT, `${name}/full.png`), fullPage: true });
    for (const [k, sel] of Object.entries(PANELS)) {
      L.panels[k] = await rect(p, sel);
      await shotEl(p, sel, `${name}/${k}.png`);
    }
    // Living UI: step forward one frame at a time with the real "1f ▶" button.
    const N = 30;
    for (let i = 0; i < N; i++) {
      await shotEl(p, '#p-video', `${name}/live/video_${String(i).padStart(3, '0')}.jpg`, 'jpeg');
      await shotEl(p, '#p-three', `${name}/live/three_${String(i).padStart(3, '0')}.jpg`, 'jpeg');
      await p.click('#btnFwd');
      await p.waitForTimeout(60);
    }
    L.liveFrames = N;
    manifest.layouts[name] = L;
    if (name === 'L') {
      // Brand wordmark as rendered by the product (for reference / lockup check)
      const bp = await b.newPage({ viewport: { width: 1600, height: 200 }, deviceScaleFactor: 6 });
      await bp.goto(URL); await bp.waitForTimeout(600);
      await bp.locator('.brand').screenshot({ path: path.join(OUT, 'brand_wordmark.png') });
      await bp.locator('#chips .chip.warn').first().screenshot({ path: path.join(OUT, 'chip_synthetic.png') }).catch(() => {});
      await bp.close();
    }
    await p.close();
  }

  // ---------- 2. Feature 1: orbit the 3D hands (real drag on the canvas) ----------
  {
    const p = await open(b, 1600, 1000);
    mk('f1');
    await p.click('#segLayout button:has-text("3D")');
    await p.waitForTimeout(400);
    const stage = await rect(p, '#stageThree');
    const cx = stage.x + stage.w * 0.5, cy = stage.y + stage.h * 0.55;
    await p.mouse.move(cx, cy);
    for (let i = 0; i < 5; i++) { await p.mouse.wheel(0, -200); await p.waitForTimeout(80); }
    await p.waitForTimeout(300);
    await p.waitForTimeout(250);
    const cursor = [];
    const shot = async (i) => {
      await shotClip(p, stage, `f1/orbit_${String(i).padStart(3, '0')}.jpg`);
    };
    // frame 0: before press
    let i = 0;
    await shot(i); cursor.push({ x: cx - stage.x, y: cy - stage.y, down: false }); i++;
    await p.mouse.down();
    const STEPS = 54;
    for (let s = 1; s <= STEPS; s++) {
      const u = s / STEPS;
      const e = 0.5 - 0.5 * Math.cos(Math.PI * u); // ease in-out like a hand
      const mx = cx - 220 * Math.sin(e * Math.PI * 1.0) + 330 * e;
      const my = cy - 70 * Math.sin(e * Math.PI);
      await p.mouse.move(mx, my);
      await p.waitForTimeout(25);
      await shot(i); cursor.push({ x: mx - stage.x, y: my - stage.y, down: true }); i++;
    }
    await p.mouse.up();
    await p.waitForTimeout(120);
    const last = cursor[cursor.length - 1];
    await shot(i); cursor.push({ x: last.x, y: last.y, down: false }); i++;
    manifest.sequences.f1 = { clip: stage, frames: i, cursor };
    // Close-up of the view controls row for a secondary layer
    await shotEl(p, '#segCameraView', 'f1/viewseg.png');
    await shotEl(p, '#segDisplay', 'f1/displayseg.png');
    await p.close();
  }

  // ---------- 3. Feature 2: scrub the reliability timeline (real drag) ----------
  // The grid reflows while scrubbing (frame details shrink when a hand is lost), so every frame is an
  // element screenshot and the cursor is stored relative to that frame's panel box.
  {
    const p = await open(b, 1600, 1320);
    mk('f2');
    const lanesCv0 = await rect(p, '#cvLanes');
    const tx = (t) => lanesCv0.x + 104 + 53.89 * t;
    const y = lanesCv0.y + 22;
    const frames = [];
    let i = 0;
    const shot = async (mx, my, down) => {
      const id = String(i).padStart(3, '0');
      const lanes = await rect(p, '#p-lanes'), video = await rect(p, '#p-video');
      await shotEl(p, '#p-lanes', `f2/lanes_${id}.jpg`, 'jpeg');
      await shotEl(p, '#p-video', `f2/video_${id}.jpg`, 'jpeg');
      frames.push({ x: mx - lanes.x, y: my - lanes.y, down, lanes, video, time: await p.locator('#timeInfo').innerText() });
      i++;
    };
    await p.mouse.move(tx(1.4), y + 30);
    await shot(tx(1.4), y + 30, false);
    await p.mouse.move(tx(1.6), y);
    await p.mouse.down();
    await p.waitForTimeout(60);
    await shot(tx(1.6), y, true);
    const STEPS = 54, T0 = 1.6, T1 = 6.4;
    for (let s = 1; s <= STEPS; s++) {
      const u = s / STEPS; const e = u < 0.5 ? 2 * u * u : 1 - Math.pow(-2 * u + 2, 2) / 2;
      const mx = tx(T0 + (T1 - T0) * e);
      await p.mouse.move(mx, y);
      await p.waitForTimeout(30);
      await shot(mx, y, true);
    }
    await p.mouse.up();
    await p.waitForTimeout(80);
    await shot(tx(T1), y, false);
    const f0 = frames[0];
    manifest.sequences.f2 = { lanes: f0.lanes, video: f0.video, frames: i, cursor: frames.map(f => ({ x: f.x, y: f.y, down: f.down })),
      perFrame: frames.map(f => ({ lanesY: f.lanes.y, time: f.time })), canvasOffset: { x: lanesCv0.x - f0.lanes.x, y: lanesCv0.y - f0.lanes.y } };
    await p.close();
  }

  // ---------- 4. Feature 3: filter to problems and jump (real clicks) ----------
  {
    const p = await open(b, 1600, 1320);
    mk('f3');
    const ev = await rect(p, '#p-events');
    const lanesP = await rect(p, '#p-lanes');
    const video = await rect(p, '#p-video');
    const inspect = await rect(p, '#p-inspect');
    const states = [];
    const SELS = { events: '#p-events', lanes: '#p-lanes', video: '#p-video', inspect: '#p-inspect' };
    const snap = async (name, mx, my) => {
      const st = { name, mouse: { x: mx, y: my }, rects: {}, scrollY: await p.evaluate(() => scrollY),
        listScroll: await p.evaluate(() => document.querySelector('#events').scrollTop) };
      for (const [k, sel] of Object.entries(SELS)) st.rects[k] = await rect(p, sel);
      st.rel = { x: mx - st.rects.events.x, y: my - st.rects.events.y };
      await shotEl(p, '#p-events', `f3/events_${name}.png`, 'png');
      await shotEl(p, '#p-lanes', `f3/lanes_${name}.jpg`, 'jpeg');
      await shotEl(p, '#p-video', `f3/video_${name}.jpg`, 'jpeg');
      await shotEl(p, '#p-inspect', `f3/inspect_${name}.jpg`, 'jpeg');
      st.time = await p.locator('#timeInfo').innerText();
      states.push(st);
    };
    const btn = await rect(p, '#segEvents button:has-text("Problems only")');
    const bx = btn.x + btn.w * 0.5, by = btn.y + btn.h * 0.55;
    await p.mouse.move(ev.x + ev.w * 0.8, ev.y + ev.h * 0.9);
    await snap('0_idle', ev.x + ev.w * 0.8, ev.y + ev.h * 0.9);
    await p.mouse.move(bx, by); await p.waitForTimeout(80);
    await snap('1_hover_filter', bx, by);
    await p.mouse.click(bx, by); await p.waitForTimeout(200);
    await snap('2_filtered', bx, by);
    const target = p.locator('#events .ev', { hasText: 'Left hand lost' }).first();
    const tb = await target.boundingBox();
    const ex = tb.x + 120, ey = tb.y + tb.height * 0.5;
    await p.mouse.move(ex, ey); await p.waitForTimeout(80);
    await snap('3_hover_event', ex, ey);
    await p.mouse.click(ex, ey); await p.waitForTimeout(250);
    await snap('4_jumped', ex, ey);
    manifest.sequences.f3 = { states,
      target: { x: tb.x, y: tb.y, w: tb.width, h: tb.height }, filterBtn: btn };
    await p.close();
  }

  fs.writeFileSync(path.join(OUT, 'manifest.json'), JSON.stringify(manifest, null, 2));
  await b.close();
  console.log('ok');
})();
