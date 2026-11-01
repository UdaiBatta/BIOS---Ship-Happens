// MOTIONIQ showreel composition. Deterministic: window.seek(t) renders time t (seconds).
// Every UI pixel is a Playwright capture from assets/ui (see scripts/capture.js).
(() => {
  'use strict';
  const Q = new URLSearchParams(location.search);
  const FMT = Q.get('fmt') || '9x16';
  const [W, H] = { '9x16': [1080, 1920], '1x1': [1080, 1080], '16x9': [1920, 1080] }[FMT];
  const IS_V = FMT === '9x16', IS_S = FMT === '1x1', IS_H = FMT === '16x9';
  const TL = window.TL, MF = window.MANIFEST;
  const UI = '../assets/ui/';
  const C = { page: '#0d0d0d', surface: '#1a1a19', ink: '#f0efec', ink2: '#c3c2b7', muted: '#898781',
    left: '#d95926', right: '#3987e5', warn: '#fab219', good: '#0ca30c' };

  // ---------------------------------------------------------------- math
  const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
  const lerp = (a, b, u) => a + (b - a) * u;
  const P = (t, a, b) => clamp((t - a) / (b - a));
  const E = {
    lin: x => x,
    outCubic: x => 1 - Math.pow(1 - x, 3),
    inCubic: x => x * x * x,
    inOutCubic: x => x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2,
    outQuart: x => 1 - Math.pow(1 - x, 4),
    outExpo: x => x >= 1 ? 1 : 1 - Math.pow(2, -10 * x),
    inExpo: x => x <= 0 ? 0 : Math.pow(2, 10 * x - 10),
    inOutExpo: x => x <= 0 ? 0 : x >= 1 ? 1 : x < 0.5 ? Math.pow(2, 20 * x - 10) / 2 : (2 - Math.pow(2, -20 * x + 10)) / 2,
    outBack: x => { const c1 = 1.9, c3 = c1 + 1; return 1 + c3 * Math.pow(x - 1, 3) + c1 * Math.pow(x - 1, 2); },
    inOutQuad: x => x < 0.5 ? 2 * x * x : 1 - Math.pow(-2 * x + 2, 2) / 2,
  };
  const tw = (t, a, b, v0, v1, e = E.outCubic) => lerp(v0, v1, e(P(t, a, b)));
  const hash = n => { const x = Math.sin(n * 127.1 + 311.7) * 43758.5453; return x - Math.floor(x); };
  const noise = x => { const i = Math.floor(x), f = x - i, u = f * f * (3 - 2 * f); return lerp(hash(i), hash(i + 1), u) * 2 - 1; };
  const decay = (t, t0, tau) => (t < t0 ? 0 : Math.exp(-(t - t0) / tau));
  const pad = (n, w) => String(n).padStart(w, '0');
  const tc = s => `${pad(Math.floor(s / 60), 2)}:${pad(Math.floor(s % 60), 2)}.${pad(Math.floor((s * 1000) % 1000), 3)}`;

  // ---------------------------------------------------------------- dom
  const stage = document.getElementById('stage');
  stage.style.width = W + 'px'; stage.style.height = H + 'px';
  const el = (tag, parent, cls, css, html) => {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (css) Object.assign(e.style, css);
    if (html !== undefined) e.innerHTML = html;
    (parent || stage).appendChild(e);
    return e;
  };
  const T = (e, o) => {
    const x = o.x || 0, y = o.y || 0, s = o.s === undefined ? 1 : o.s;
    const sx = o.sx === undefined ? s : o.sx, sy = o.sy === undefined ? s : o.sy;
    let tr = `translate3d(${x.toFixed(2)}px,${y.toFixed(2)}px,0)`;
    if (o.rx) tr += ` rotateX(${o.rx}deg)`;
    if (o.ry) tr += ` rotateY(${o.ry}deg)`;
    if (o.r) tr += ` rotate(${o.r}deg)`;
    if (o.skx) tr += ` skewX(${o.skx}deg)`;
    if (o.sky) tr += ` skewY(${o.sky}deg)`;
    tr += ` scale(${sx},${sy})`;
    e.style.transform = tr;
    if (o.o !== undefined) { e.style.opacity = clamp(o.o); e.style.visibility = o.o <= 0.002 ? 'hidden' : 'visible'; }
    const b = o.blur || 0;
    e.style.filter = b > 0.15 ? `blur(${b.toFixed(2)}px)` : 'none';
  };
  const vis = (e, v) => { e.style.display = v ? '' : 'none'; };
  const pending = [];
  const setSrc = (img, src) => {
    if (img._src === src) return;
    img._src = src; img.src = src;
    pending.push(img.decode().catch(() => {}));
  };
  // preload helper (warms the cache, not required for correctness)
  const meas = el('span', document.body, null, { position: 'absolute', left: '-9999px', top: '0', whiteSpace: 'pre' });
  const textW = (text, family, weight, size, ls = 0, tt = 'none') => {
    Object.assign(meas.style, { fontFamily: family, fontWeight: weight, fontSize: size + 'px', letterSpacing: ls + 'em', textTransform: tt });
    meas.textContent = text;
    return meas.getBoundingClientRect().width;
  };
  const FAM = { head: 'Arial, "Liberation Sans", sans-serif', ui: 'system-ui, -apple-system, "Segoe UI", sans-serif', mono: '"DejaVu Sans Mono", "Liberation Mono", monospace' };
  const fitHead = (text, maxW) => 100 * maxW / textW(text, FAM.head, 700, 100, -0.03, 'uppercase');

  // ---------------------------------------------------------------- layers
  const bg = el('canvas', stage, 'layer'); bg.width = W; bg.height = H;
  const bgx = bg.getContext('2d');
  const cam = el('div', stage, 'layer', { transformOrigin: '50% 50%' });
  const world = el('div', cam, 'layer', { perspective: '2400px' });
  const fx = el('canvas', stage, 'layer'); fx.width = W; fx.height = H;
  const fxx = fx.getContext('2d');
  const hud = el('div', stage, 'layer');
  const vignette = el('div', stage, 'layer', { background: 'radial-gradient(ellipse at 50% 45%, rgba(0,0,0,0) 55%, rgba(0,0,0,0.55) 100%)' });
  const grain = el('div', stage, 'layer', { mixBlendMode: 'overlay', opacity: '0.16', backgroundSize: '384px 384px' });

  // ---------------------------------------------------------------- per-format layout
  const M = IS_H ? 80 : (IS_S ? 60 : 72);
  const LAY = {
    '9x16': {
      hook: { lines: [['WHICH'], ['SECONDS'], ['CAN', 'YOU'], ['TRUST?']], maxW: 936, maxH: 960, cy: 0.5 },
      sheet: { LK: 'P', area: [40, 150, 1000, 1540] },
      wm: { maxW: 900, cy: 0.47 },
      caps: { mode: 'stack', x: 72, y: 1560, maxW: 936, size: 72, scrim: true },
      f1: { head: { x: 72, y: 210, maxW: 936, max: 260 }, sub: { x: 72, y: 0 }, hero: { x: 40, y: 760, w: 1000 },
        chips: { x: 72, y: 1380, k: 2.0 }, tags: { x: 72, y: 1500, dir: 'row' } },
      f2: { head: { x: 72, y: 190, maxW: 936, max: 170 }, sub: { x: 72 }, video: { x: 60, y: 540, w: 960 },
        lanes: { x: 40, y: 1330, w: 1000, crop: 760 }, clock: { x: 72, y: 1640, size: 150 } },
      f3: { head: { x: 72, y: 190, maxW: 936, max: 170 }, sub: { x: 72 }, ev0: { x: 149, y: 540, k: 2.3 }, ev1: { x: 72, y: 520, k: 1.42 },
        video: { x: 40, y: 1120, w: 1000 }, lost: { x: 600, y: 610, w: 400 } },
      metric: { num: { cx: 540, y: 250, maxW: 820 }, label: { cx: 540, y: 0, maxW: 860 }, grid: { x: 43, y: 1150, cols: 20, cell: 44, gap: 6 } },
      lockup: { maxW: 880, cy: 0.47 },
    },
    '1x1': {
      hook: { lines: [['WHICH'], ['SECONDS'], ['CAN', 'YOU'], ['TRUST?']], maxW: 880, maxH: 820, cy: 0.52 },
      sheet: { LK: 'L', area: [60, 110, 960, 800] },
      wm: { maxW: 880, cy: 0.5 },
      caps: { mode: 'swap', x: 60, y: 948, maxW: 960, size: 64, scrim: false },
      f1: { head: { x: 60, y: 110, maxW: 960, max: 150, oneLine: true }, sub: { x: 60 }, hero: { x: 90, y: 330, w: 900 },
        chips: { x: 90, y: 880, k: 1.6 }, tags: { x: 600, y: 890, dir: 'col' } },
      f2: { head: { x: 60, y: 110, maxW: 960, max: 100, oneLine: true }, sub: { x: 60 }, video: { x: 60, y: 290, w: 560 },
        lanes: { x: 60, y: 820, w: 960, crop: 760 }, clock: { x: 650, y: 360, size: 84 } },
      f3: { head: { x: 60, y: 110, maxW: 960, max: 100, oneLine: true }, sub: { x: 60 }, ev0: { x: 60, y: 285, k: 1.75 }, ev1: { x: 60, y: 285, k: 1.2 },
        video: { x: 490, y: 300, w: 530 }, lost: { x: 490, y: 670, w: 500 }, side: false },
      metric: { num: { cx: 540, y: 104, maxW: 520 }, label: { cx: 540, y: 0, maxW: 720 }, grid: { x: 63, y: 590, cols: 24, cell: 34, gap: 6 } },
      lockup: { maxW: 860, cy: 0.46 },
    },
    '16x9': {
      hook: { lines: [['WHICH', 'SECONDS'], ['CAN', 'YOU', 'TRUST?']], maxW: 1680, maxH: 760, cy: 0.5 },
      sheet: { LK: 'L', area: [700, 90, 1160, 930] },
      wm: { maxW: 1150, cy: 0.47 },
      caps: { mode: 'stack', x: 100, y: 360, maxW: 560, size: 64, scrim: false },
      f1: { head: { x: 100, y: 250, maxW: 640, max: 230 }, sub: { x: 100 }, hero: { x: 780, y: 190, w: 1060 },
        chips: { x: 780, y: 840, k: 1.8 }, tags: { x: 100, y: 0, dir: 'row' } },
      f2: { head: { x: 100, y: 120, maxW: 800, max: 120 }, sub: { x: 100 }, video: { x: 1000, y: 90, w: 820 },
        lanes: { x: 100, y: 800, w: 1720, crop: 1216 }, clock: { x: 100, y: 470, size: 120 } },
      f3: { head: { x: 100, y: 120, maxW: 680, max: 120 }, sub: { x: 100 }, ev0: { x: 100, y: 390, k: 1.65 }, ev1: { x: 100, y: 390, k: 1.65 },
        video: { x: 820, y: 90, w: 1000 }, lanes: { x: 820, y: 760, w: 1000, crop: 760 }, lost: null, side: true },
      metric: { num: { cx: 0, x: 100, y: 130, maxW: 760 }, label: { x: 100, y: 0, maxW: 760 }, grid: { x: 990, y: 140, cols: 16, cell: 46, gap: 8 } },
      lockup: { maxW: 1100, cy: 0.45 },
    },
  }[FMT];

  // ---------------------------------------------------------------- shared builders
  function makeHeadline(parent, lines, o) {
    // lines: array of arrays of [text, color]
    const plain = lines.map(l => l.map(s => s[0]).join(''));
    let size = Math.min(o.max || 999, ...plain.map(s => fitHead(s, o.maxW)));
    const root = el('div', parent, 'abs head', { fontSize: size + 'px' });
    const items = lines.map((l, i) => {
      const mask = el('div', root, 'mask', { position: 'relative' });
      const inner = el('div', mask, null, {}, l.map(([s, c]) => `<span style="color:${c || C.ink}">${s}</span>`).join(''));
      return { mask, inner };
    });
    const h = size * 0.9 * lines.length;
    T(root, { x: o.x, y: o.y });
    return { root, items, size, h, x: o.x, y: o.y };
  }
  function revealHeadline(hd, t, t0, stagger = 0.125, dur = 0.42) {
    hd.items.forEach((it, i) => {
      const u = P(t, t0 + i * stagger, t0 + i * stagger + dur);
      const e = E.outExpo(u);
      T(it.inner, { y: (1 - e) * hd.size * 1.05, sky: (1 - e) * 8, o: u > 0 ? 1 : 0 });
    });
  }
  function makeSub(parent, text, o) {
    const e = el('div', parent, 'abs', { fontFamily: FAM.head, fontSize: (o.size || 30) + 'px', color: C.ink2, whiteSpace: 'nowrap', letterSpacing: '0.01em' }, text);
    return e;
  }
  function makeCard(parent, w, h, src, o = {}) {
    const wrap = el('div', parent, 'abs ctr', { width: w + 'px', height: h + 'px' });
    const clip = el('div', wrap, 'card-clip', { borderRadius: (o.radius === undefined ? 10 : o.radius) + 'px' });
    const img = el('img', clip, null, { width: (o.imgW || w) + 'px', height: (o.imgH || h) + 'px' });
    if (src) setSrc(img, src);
    const glow = el('div', wrap, null, { position: 'absolute', inset: '-2px', borderRadius: '12px', boxShadow: `0 0 0 3px ${C.left}`, opacity: 0 });
    return { wrap, clip, img, glow, w, h };
  }
  // place card so its top-left lands on (X,Y) at scale k (transform-origin is the centre)
  function placeCard(cd, X, Y, k, extra = {}) {
    T(cd.wrap, Object.assign({ x: X - cd.w / 2 + k * cd.w / 2, y: Y - cd.h / 2 + k * cd.h / 2, s: k }, extra));
  }
  const CURSOR_SVG = '<svg width="30" height="40" viewBox="0 0 30 40"><path d="M2.5 2.5 L2.5 31 L9.6 24.6 L14.3 35.4 L19.4 33.2 L14.8 22.6 L24.2 22.6 Z" fill="#fff" stroke="#0b0b0b" stroke-width="2.2" stroke-linejoin="round"/></svg>';
  function makeCursor(parent) {
    const c = el('div', parent, 'abs', { width: '30px', height: '40px', transformOrigin: '2.5px 2.5px', filter: 'drop-shadow(0 6px 10px rgba(0,0,0,.5))', zIndex: 5 }, CURSOR_SVG);
    const ring = el('div', parent, 'ring');
    const ring2 = el('div', parent, 'ring', { borderColor: C.right });
    return { c, ring, ring2 };
  }
  // cursor in card-local CSS coords; k = card scale so cursor keeps a constant on-screen size
  function setCursor(cu, x, y, k, o, down, clicks, t) {
    const sz = (IS_H ? 1.5 : 1.7) / k;
    const press = down ? 0.84 : 1;
    cu.c.style.left = (x - 2.5) + 'px'; cu.c.style.top = (y - 2.5) + 'px';
    T(cu.c, { s: sz * press, o });
    // click rings
    let best = null;
    for (const ct of clicks) if (t >= ct && t < ct + 0.45) best = ct;
    [cu.ring, cu.ring2].forEach((r, i) => {
      if (best === null) { r.style.visibility = 'hidden'; return; }
      const u = P(t, best + i * 0.06, best + 0.4 + i * 0.06);
      const rad = lerp(6, 70, E.outCubic(u)) / k;
      Object.assign(r.style, { left: (x - rad) + 'px', top: (y - rad) + 'px', width: 2 * rad + 'px', height: 2 * rad + 'px', borderWidth: (3 / k) + 'px', visibility: 'visible', opacity: (1 - u) * (u > 0 ? 1 : 0) });
    });
  }
  function makeTag(parent, text, bgc, fg, size) {
    const tg = el('div', parent, 'tag', { background: bgc, color: fg, fontSize: size + 'px' }, text);
    return tg;
  }
  const popIn = (t, t0, d = 0.32) => { const u = P(t, t0, t0 + d); return { s: lerp(0.4, 1, E.outBack(u)), o: clamp(u * 4) }; };

  // ---------------------------------------------------------------- impacts / camera
  const words = TL.words;
  const impacts = [];
  words.forEach(([w, t], i) => impacts.push([t, i === 4 ? 26 : 12]));
  impacts.push([TL.drop, 30]);
  TL.panels.forEach(([, t]) => impacts.push([t, 6]));
  impacts.push([TL.f1.press, 4], [TL.f2.press, 4], [TL.f3.clickFilter, 5], [TL.f3.clickEvent, 8]);
  impacts.push([TL.metric.lock, 16], [TL.metric.lockup, 28], [7.0, 10], [10.0, 10], [13.0, 10]);
  const kicks = [];
  for (let b = 6; b < 32; b++) kicks.push(b * 0.5);       // 3.0 .. 15.5 four-on-the-floor
  kicks.push(16.0, 17.0, 18.0);
  function camera(t) {
    let sh = 0;
    for (const [ti, s] of impacts) sh += s * decay(t, ti, 0.09);
    let pulse = 0;
    for (const k of kicks) pulse = Math.max(pulse, decay(t, k, 0.07));
    const sx = noise(t * 37.0) * sh, sy = noise(t * 41.0 + 9) * sh, rr = noise(t * 23 + 3) * sh * 0.03;
    return { x: sx, y: sy, r: rr, s: 1 + pulse * 0.010 };
  }

  // ---------------------------------------------------------------- background (grid floor motif, from the 3D panel)
  function drawBg(t) {
    bgx.setTransform(1, 0, 0, 1, 0, 0);
    bgx.fillStyle = C.page; bgx.fillRect(0, 0, W, H);
    // ambient glows: wearer-left orange, wearer-right blue
    const g1 = bgx.createRadialGradient(W * 0.1, H * 0.85, 0, W * 0.1, H * 0.85, Math.max(W, H) * 0.7);
    g1.addColorStop(0, 'rgba(217,89,38,0.16)'); g1.addColorStop(1, 'rgba(217,89,38,0)');
    bgx.fillStyle = g1; bgx.fillRect(0, 0, W, H);
    const g2 = bgx.createRadialGradient(W * 0.95, H * 0.1, 0, W * 0.95, H * 0.1, Math.max(W, H) * 0.7);
    g2.addColorStop(0, 'rgba(57,135,229,0.14)'); g2.addColorStop(1, 'rgba(57,135,229,0)');
    bgx.fillStyle = g2; bgx.fillRect(0, 0, W, H);
    // perspective floor
    const hy = H * (IS_V ? 0.62 : 0.6), camH = H * 0.9, f = 1.0;
    const speed = t < 3 ? (0.8 + 9 * Math.pow(P(t, 1.8, 3.0), 3)) : 1.2;
    const z0 = t * 1.2 + 4.5 * Math.pow(P(t, 1.8, 3.0), 4) + (t > 16 ? -0.3 * (t - 16) : 0);
    let pulse = 0; for (const k of kicks) pulse = Math.max(pulse, decay(t, k, 0.12));
    const alpha = 0.22 + 0.18 * pulse + (t < 3 ? 0.25 * P(t, 2.0, 2.9) : 0);
    bgx.lineWidth = 1.5;
    for (let i = 0; i < 26; i++) {
      const z = (i + 1) - (z0 % 1);
      const y = hy + camH * f / (z * 1.25);
      if (y > H + 4) continue;
      const a = alpha * clamp(1.4 - z / 18);
      bgx.strokeStyle = `rgba(80,80,76,${a})`;
      bgx.beginPath(); bgx.moveTo(0, y); bgx.lineTo(W, y); bgx.stroke();
    }
    for (let i = -24; i <= 24; i++) {
      const xb = W / 2 + i * W * 0.16;
      bgx.strokeStyle = `rgba(80,80,76,${alpha * 0.9})`;
      bgx.beginPath(); bgx.moveTo(W / 2 + (xb - W / 2) * 0.02, hy); bgx.lineTo(W / 2 + (xb - W / 2) * 3.2, H * 1.6); bgx.stroke();
    }
    // horizon fade
    const hg = bgx.createLinearGradient(0, hy - 2, 0, hy + H * 0.12);
    hg.addColorStop(0, 'rgba(13,13,13,1)'); hg.addColorStop(1, 'rgba(13,13,13,0)');
    bgx.fillStyle = hg; bgx.fillRect(0, hy - 2, W, H * 0.12 + 2);
    void speed;
  }

  // ================================================================ SCENE 1: HOOK
  const hook = (() => {
    const root = el('div', world, 'layer');
    const flash = el('div', root, 'layer', { background: C.left, opacity: 0 });
    const L = LAY.hook;
    const lineTexts = L.lines.map(l => l.join(' '));
    let size = Math.min(...lineTexts.map(s => fitHead(s, L.maxW)));
    size = Math.min(size, L.maxH / (L.lines.length * 0.9));
    const stack = el('div', root, 'abs head', { fontSize: size + 'px', textAlign: 'center', width: W + 'px', lineHeight: '0.9', transformOrigin: '0 0' });
    const spans = {};
    L.lines.forEach(ws => {
      const line = el('div', stack, null, {});
      ws.forEach((w, j) => {
        const s = el('span', line, null, { display: 'inline-block', transformOrigin: '50% 55%', marginRight: j < ws.length - 1 ? '0.24em' : '0' }, w);
        spans[w] = s;
      });
    });
    const sh = L.lines.length * 0.9 * size;
    const top = H * L.cy - sh / 2;
    T(stack, { x: 0, y: top });
    spans['TRUST?'].style.color = C.left;
    const kicker = el('div', root, 'abs mono', { fontSize: (IS_H ? 24 : 26) + 'px', letterSpacing: '0.32em', color: C.ink2, width: W + 'px', textAlign: 'center' }, 'FACTORY POV · HAND MOTION');
    const rec = el('div', root, 'abs mono', { fontSize: (IS_H ? 24 : 26) + 'px', letterSpacing: '0.12em', color: C.muted, width: W + 'px', textAlign: 'center' }, '');
    T(kicker, { y: top - (IS_V ? 170 : 120) });
    T(rec, { y: top - (IS_V ? 125 : 82) });
    let slots = null, origin = null;
    function measure() {
      slots = {};
      for (const [w] of words) {
        const r = spans[w].getBoundingClientRect();
        slots[w] = { cx: r.left + r.width / 2, cy: r.top + r.height / 2 };
      }
      // zoom-through origin: the counter of the "O" in SECONDS
      const tn = spans['SECONDS'].firstChild; const rg = document.createRange();
      rg.setStart(tn, 3); rg.setEnd(tn, 4);
      const r = rg.getBoundingClientRect();
      origin = { x: r.left + r.width / 2, y: r.top + r.height * 0.52 };
    }
    function update(t) {
      const on = t < TL.hookZoom[1] + 0.02; vis(root, on); if (!on) return;
      if (!slots) measure();
      words.forEach(([w, t0], i) => {
        const s = spans[w];
        if (t < t0) { s.style.visibility = 'hidden'; return; }
        const u = P(t, t0, t0 + 0.3), e = E.outExpo(u);
        const sl = slots[w];
        const dx = (W / 2 - sl.cx) * (1 - e), dy = (H / 2 - sl.cy) * (1 - e);
        const sc = lerp(i === 4 ? 3.6 : 2.8, 1, e);
        const blur = 26 * (1 - E.outCubic(P(t, t0, t0 + 0.14)));
        T(s, { x: dx, y: dy, s: sc, o: P(t, t0, t0 + 0.035), blur });
        if (w === 'TRUST?') {
          const g = P(t, 2.05, 2.75);
          const j = (Math.floor(t * 30) % 2 ? 1 : -1) * (6 + 22 * g) * (Math.abs(noise(t * 18)) > 0.25 ? 1 : 0.2);
          s.style.textShadow = `${j}px 0 0 ${C.right}, ${-j * 0.6}px 0 0 rgba(240,239,236,0.55)`;
        }
      });
      // background colour hits per word
      const fl = [[0.5, C.left, 0.9], [1.5, C.right, 0.9], [2.0, C.ink, 0.85]];
      let fa = 0, fc = C.left;
      for (const [ti, c, a] of fl) { const d = decay(t, ti, 0.085) * a; if (d > fa) { fa = d; fc = c; } }
      flash.style.background = fc; flash.style.opacity = fa;
      T(kicker, { y: top - (IS_V ? 170 : 120), o: P(t, 0.1, 0.3) * (1 - P(t, 2.7, 2.8)) });
      const secs = Math.pow(t, 2.2) * 5200;
      rec.textContent = `● REC  ${pad(Math.floor(secs / 3600), 2)}:${pad(Math.floor(secs / 60) % 60, 2)}:${pad(Math.floor(secs) % 60, 2)}:${pad(Math.floor(secs * 30) % 30, 2)}`;
      T(rec, { y: top - (IS_V ? 125 : 82), o: P(t, 0.2, 0.4) * (1 - P(t, 2.7, 2.8)) });
      // zoom-through the O of SECONDS into the product
      const z = E.inExpo(P(t, TL.hookZoom[0], TL.hookZoom[1]));
      const zs = 1 + z * 60;
      stack.style.transformOrigin = `${origin.x}px ${origin.y - top}px`;
      T(stack, { x: 0, y: top, s: zs, blur: z * 10 });
    }
    return { update, measure };
  })();

  // ================================================================ SCENE 2: PRODUCT (wordmark + UI assembles)
  const product = (() => {
    const root = el('div', world, 'layer');
    const LK = LAY.sheet.LK, lay = MF.layouts[LK];
    const page = lay.page;
    const [ax, ay, aw, ah] = LAY.sheet.area;
    const k = Math.min(aw / page.w, ah / page.h);
    const sx = ax + (aw - page.w * k) / 2, sy = ay;
    const sheetWrap = el('div', root, 'abs', { width: page.w + 'px', height: page.h + 'px', perspective: '1800px' });
    const win = el('div', sheetWrap, 'abs', { width: page.w + 'px', height: page.h + 'px', background: C.page, borderRadius: '16px',
      boxShadow: '0 60px 140px rgba(0,0,0,.7), 0 0 0 1px rgba(255,255,255,.10)' });
    const order = TL.panels.map(p => p[0]);
    const dirs = { header: [0, 0, 0, 0], controls: [0, -260, 55, 0], video: [-900, 120, 0, -40], three: [900, 120, 0, 40],
      lanes: [0, 700, -45, 0], inspect: [-760, 380, 0, -32], events: [760, 380, 0, 32] };
    const panels = {};
    order.forEach((name, i) => {
      const r = lay.panels[name];
      const cd = makeCard(sheetWrap, r.w, r.h, UI + `${LK}/${name}.png`, { radius: name === 'header' || name === 'controls' ? 0 : 10 });
      cd.r = r; cd.land = TL.panels[i][1]; cd.dir = dirs[name];
      cd.clip.style.boxShadow = name === 'header' || name === 'controls' ? 'none' : '0 30px 70px rgba(0,0,0,.55), 0 0 0 1px rgba(255,255,255,.06)';
      cd.glow.style.boxShadow = `0 0 0 3px ${i % 2 ? C.right : C.left}, 0 0 40px ${i % 2 ? C.right : C.left}`;
      panels[name] = cd;
    });
    // big wordmark (product UI typeface, same tracking as the header .brand: 0.06em)
    const wmText = 'MOTIONIQ';
    const wmSize = 100 * LAY.wm.maxW / textW(wmText, FAM.ui, 700, 100, 0.06);
    const wm = el('div', root, 'abs', { fontFamily: FAM.ui, fontWeight: 700, fontSize: wmSize + 'px', letterSpacing: '0.06em', lineHeight: '1.4', whiteSpace: 'nowrap', color: C.ink });
    const letters = [...wmText].map(ch => el('span', wm, null, { display: 'inline-block', transformOrigin: '50% 60%' }, ch));
    const wmW = textW(wmText, FAM.ui, 700, wmSize, 0.06);
    const wmX = (W - wmW) / 2, wmY = H * LAY.wm.cy - wmSize * 0.7;
    const kick = el('div', root, 'abs mono', { fontSize: (IS_H ? 26 : 28) + 'px', letterSpacing: '0.34em', color: C.ink2, width: W + 'px', textAlign: 'center' }, 'BIOS · SHIP HAPPENS');
    const barL = el('div', root, 'abs', { height: '10px', background: C.left, width: '10px' });
    const barR = el('div', root, 'abs', { height: '10px', background: C.right, width: '10px' });
    // brand target in stage coords
    const br = lay.brand;
    const tgtX = sx + br.x * k, tgtY = sy + br.y * k, tgtS = (15 * k) / wmSize;
    // captions
    const caps = TL.productCaptions.map(([txt], i) => {
      const L = LAY.caps;
      const size = Math.min(L.size, fitHead(txt, L.maxW));
      const c = el('div', root, 'abs head', { fontSize: size + 'px', color: i === 1 ? C.ink : C.ink }, '');
      const colors = [C.ink, C.ink, C.ink2];
      c.innerHTML = txt.replace('IN.', `<span style="color:${C.left}">IN.</span>`).replace('OUT.', `<span style="color:${C.right}">OUT.</span>`);
      c.style.color = colors[i];
      return { c, size };
    });
    const scrim = el('div', root, 'layer', { background: 'linear-gradient(to bottom, rgba(13,13,13,0) 60%, rgba(13,13,13,0.96) 82%)', opacity: 0 });
    root.insertBefore(scrim, caps[0].c);
    const threeCenter = () => {
      const r = lay.panels.three;
      return { x: sx + (r.x + r.w / 2) * k, y: sy + (r.y + r.h / 2) * k };
    };
    function update(t) {
      const on = t >= TL.drop - 0.02 && t < 7.02; vis(root, on); if (!on) return;
      const [m0, m1] = TL.wordmark.morph;
      // --- wordmark slam
      letters.forEach((s, i) => {
        const t0 = TL.drop + i * 0.022;
        const u = P(t, t0, t0 + 0.32), e = E.outExpo(u);
        const dir = i % 2 ? 1 : -1;
        T(s, { y: dir * (1 - e) * wmSize * 1.1, s: lerp(1.9, 1, e), r: dir * (1 - e) * 14, o: P(t, t0, t0 + 0.04), blur: 18 * (1 - E.outCubic(P(t, t0, t0 + 0.16))) });
      });
      const mu = E.inOutCubic(P(t, m0, m1));
      const breathe = 1 + 0.03 * P(t, 3.2, m0);
      const wsx = lerp(breathe, tgtS, mu);
      // keep the wordmark centred while it breathes, then fly into the header brand
      const cxOff = (wmW * (1 - breathe)) / 2;
      T(wm, { x: lerp(wmX + cxOff, tgtX, mu), y: lerp(wmY + wmSize * 1.4 * (1 - breathe) / 2, tgtY, mu), s: wsx, o: t < m1 + 0.02 ? 1 : 0 });
      T(kick, { y: wmY - (IS_V ? 70 : 64), o: P(t, 3.2, 3.35) * (1 - P(t, m0, m0 + 0.1)) });
      // underline bars: left hand + right hand meet under the logo
      const bu = E.outExpo(P(t, 3.05, 3.45)), bo = 1 - P(t, m0, m0 + 0.12);
      const by = wmY + wmSize * 1.32, half = wmW / 2;
      T(barL, { x: W / 2 - half * bu, y: by, sx: Math.max(0.01, half * bu - 8) / 10, o: bo });
      T(barR, { x: W / 2 + 8, y: by, sx: Math.max(0.01, half * bu - 8) / 10, o: bo });
      // --- window + panels
      const winO = P(t, m0 - 0.15, m0 + 0.1);
      const push = 1 + 0.06 * E.inOutCubic(P(t, 5.5, 6.75));
      const z = E.inExpo(P(t, TL.zoomToF1[0], TL.zoomToF1[1]));
      const tc3 = threeCenter();
      // sheet transform (scale about the 3D panel centre for the zoom-through)
      const S = k * push * (1 + z * 3.2);
      const ox = tc3.x, oy = tc3.y;
      const X = ox + (sx - ox) * (S / k), Y = oy + (sy - oy) * (S / k);
      T(sheetWrap, { x: X, y: Y, s: S, o: winO, blur: z * 14 });
      T(win, { o: 1 });
      order.forEach((name, i) => {
        const cd = panels[name], r = cd.r;
        if (name === 'header') {
          const hu = E.outExpo(P(t, cd.land, cd.land + 0.22));
          cd.clip.style.clipPath = `inset(0 ${(1 - hu) * 100}% 0 0)`;
          placeCard(cd, r.x, r.y, 1, { o: t >= m1 ? 1 : 0 });
          return;
        }
        const u = P(t, cd.land - 0.3, cd.land), e = E.outCubic(u);
        const [dx, dy, rx, ry] = cd.dir;
        placeCard(cd, r.x + dx * (1 - e), r.y + dy * (1 - e), lerp(0.82, 1, e), { rx: rx * (1 - e), ry: ry * (1 - e), o: clamp(u * 3), blur: 10 * (1 - e) });
        cd.glow.style.opacity = t >= cd.land ? 0.9 * decay(t, cd.land, 0.12) : 0;
      });
      // living UI: the real playback sequence (30 consecutive frames)
      const [l0, l1] = TL.live;
      const li = t < l0 ? 0 : Math.min(29, Math.floor(P(t, l0, l1) * 30));
      setSrc(panels.video.img, li === 0 ? UI + `${LK}/video.png` : UI + `${LK}/live/video_${pad(li, 3)}.jpg`);
      setSrc(panels.three.img, li === 0 ? UI + `${LK}/three.png` : UI + `${LK}/live/three_${pad(li, 3)}.jpg`);
      // captions
      const L = LAY.caps;
      scrim.style.opacity = L.scrim ? P(t, 5.3, 5.6) * (1 - z) : 0;
      caps.forEach((cp, i) => {
        const t0 = TL.productCaptions[i][1];
        const u = P(t, t0, t0 + 0.35), e = E.outExpo(u);
        let y, o = (u > 0 ? 1 : 0) * (1 - z);
        if (L.mode === 'stack') y = L.y + i * cp.size * 1.0;
        else { y = L.y; const nxt = TL.productCaptions[i + 1]; if (nxt) o *= 1 - P(t, nxt[1] - 0.06, nxt[1]); }
        T(cp.c, { x: L.x - (1 - e) * 60, y: y + (1 - e) * 20, o, blur: (1 - e) * 8, skx: (1 - e) * -10 });
      });
    }
    return { update, threeCenter, k, sx, sy };
  })();

  // ================================================================ SCENE 3: F1 orbit the 3D hands
  const f1 = (() => {
    const L = LAY.f1, SQ = MF.sequences.f1;
    const root = el('div', world, 'layer');
    const head = makeHeadline(root, L.head.oneLine ? [[['HANDS IN ', C.ink], ['3D.', C.right]]] : [[['HANDS', C.ink]], [['IN ', C.ink], ['3D.', C.right]]], L.head);
    const sub = makeSub(root, 'Drag to orbit. Wrist-centred 3D posture.', { size: IS_H ? 28 : 30 });
    const subY = head.y + head.h + 26;
    const cw = SQ.clip.w, ch = SQ.clip.h;
    const card = makeCard(root, cw, ch, UI + 'f1/orbit_000.jpg', { radius: 8 });
    const kh = L.hero.w / cw;
    const cu = makeCursor(card.wrap);
    const chipA = makeCard(root, 240, 30, UI + 'f1/displayseg.png', { radius: 6 });
    const chipB = makeCard(root, 156, 30, UI + 'f1/viewseg.png', { radius: 6 });
    const tagL = makeTag(root, '● Wearer left', 'rgba(217,89,38,0.16)', C.left, IS_H ? 26 : 28);
    const tagR = makeTag(root, '● Wearer right', 'rgba(57,135,229,0.16)', C.right, IS_H ? 26 : 28);
    const N = SQ.frames; // 56
    function update(t) {
      const on = t >= 6.98 && t < (TL.f1.wipe[0] + TL.f1.wipe[1]) / 2; vis(root, on); if (!on) return;
      const { press, release } = TL.f1;
      revealHeadline(head, t, 7.0);
      T(sub, { x: L.head.x, y: subY + (1 - E.outExpo(P(t, 7.2, 7.6))) * 30, o: P(t, 7.2, 7.4) });
      // hero card: zoom in from the previous scene, then drift
      const eu = E.outExpo(P(t, 7.0, 7.45));
      const drift = P(t, 7.0, 10.0);
      placeCard(card, L.hero.x, L.hero.y, kh * lerp(1.35, 1, eu), { ry: lerp(-9, 5, drift), rx: lerp(6, -2, drift), o: P(t, 6.98, 7.08), blur: 18 * (1 - eu) });
      let idx, f;
      if (t < press) { idx = 0; f = 0; }
      else if (t < release) { const u = P(t, press, release); f = 1 + u * 53; idx = 1 + Math.min(53, Math.floor(u * 54)); }
      else { idx = N - 1; f = N - 2; }
      setSrc(card.img, UI + `f1/orbit_${pad(idx, 3)}.jpg`);
      // push into the real capture while dragging (crop, not redraw), back out on release
      const zin = E.inOutCubic(P(t, press - 0.15, press + 0.6)) * (1 - E.inOutCubic(P(t, release + 0.05, release + 0.5)));
      const Z = 1 + 0.42 * zin, ox = cw * 0.64, oy = ch * 0.56;
      card.img.style.transformOrigin = `${ox}px ${oy}px`;
      card.img.style.transform = `scale(${Z})`;
      const zmap = (px, py) => [ox + (px - ox) * Z, oy + (py - oy) * Z];
      // cursor: approach, drag along the recorded path, release, leave
      const cs = SQ.cursor;
      let x, y;
      if (t < press) {
        const a = E.outCubic(P(t, 7.05, press - 0.05));
        x = lerp(cw * 1.05, cs[0].x, a); y = lerp(ch * 1.15, cs[0].y, a);
      } else {
        const i0 = Math.min(cs.length - 2, Math.floor(f)), fr = f - i0;
        x = lerp(cs[i0].x, cs[i0 + 1].x, fr); y = lerp(cs[i0].y, cs[i0 + 1].y, fr);
        const lv = E.inCubic(P(t, release + 0.25, release + 0.7));
        x += lv * 260; y += lv * 220;
      }
      [x, y] = zmap(x, y);
      setCursor(cu, x, y, kh, P(t, 7.05, 7.12) * (1 - P(t, release + 0.5, release + 0.7)), t >= press && t < release, [press, release], t);
      // real UI controls + deck labels
      const pa = popIn(t, TL.f1.chips[0]), pb = popIn(t, TL.f1.chips[1]);
      const ck = L.chips.k;
      placeCard(chipA, L.chips.x, L.chips.y, ck * pa.s, { o: pa.o });
      placeCard(chipB, L.chips.x + 240 * ck + 28, L.chips.y, ck * pb.s, { o: pb.o });
      const ta = popIn(t, 7.75), tb = popIn(t, 8.0);
      const tgY = L.tags.y || (subY + 80);
      if (L.tags.dir === 'row') {
        T(tagL, { x: L.tags.x, y: tgY, s: ta.s, o: ta.o });
        T(tagR, { x: L.tags.x + (IS_H ? 250 : 280), y: tgY, s: tb.s, o: tb.o });
      } else {
        T(tagL, { x: L.tags.x, y: tgY, s: ta.s, o: ta.o });
        T(tagR, { x: L.tags.x, y: tgY + 58, s: tb.s, o: tb.o });
      }
      root.style.opacity = 1;
    }
    return { update };
  })();

  // ================================================================ SCENE 4: F2 scrub the reliability timeline
  const f2 = (() => {
    const L = LAY.f2, SQ = MF.sequences.f2;
    const root = el('div', world, 'layer');
    const head = makeHeadline(root, L.head.oneLine ? [[['EVERY SECOND, ', C.ink], ['GRADED.', C.left]]] : [[['EVERY SECOND,', C.ink]], [['GRADED.', C.left]]], L.head);
    const sub = makeSub(root, 'Observed · predicted · lost. Every state explicit.', { size: IS_H ? 28 : 30 });
    const subY = head.y + head.h + 26;
    const vr = SQ.video, lr = SQ.lanes;
    const vcard = makeCard(root, vr.w, vr.h, UI + 'f2/video_000.jpg');
    const crop = L.lanes.crop, CT = 88; // crop the panel's title/buttons rows: keep legend + lanes + axis
    const lcard = makeCard(root, crop, lr.h - CT, UI + 'f2/lanes_000.jpg', { imgW: lr.w, imgH: lr.h });
    lcard.img.style.top = -CT + 'px';
    const kv = L.video.w / vr.w, kl = L.lanes.w / crop;
    const cu = makeCursor(lcard.wrap);
    const clock = el('div', root, 'abs mono', { fontSize: L.clock.size + 'px', fontWeight: 700, color: C.ink, letterSpacing: '-0.04em', whiteSpace: 'nowrap' }, '');
    const clockLbl = el('div', root, 'abs mono', { fontSize: (IS_H ? 22 : 24) + 'px', color: C.muted, letterSpacing: '0.2em' }, 'PLAYHEAD');
    // annotation tags pinned to real event times on the timeline (lanes canvas x = 104 + 53.89 t)
    const canvasX = SQ.canvasOffset.x; // #cvLanes offset inside #p-lanes
    const tx = s => canvasX + 104 + 53.89 * s;
    const ease = E.inOutQuad, T0 = 1.6, T1 = 6.4;
    const scrubT = u => T0 + (T1 - T0) * ease(u);
    const solve = target => { let lo = 0, hi = 1; for (let i = 0; i < 40; i++) { const m = (lo + hi) / 2; if (scrubT(m) < target) lo = m; else hi = m; } return lo; };
    const marks = [[3.2, 'Predicted · 2D only', 'rgba(110,120,135,0.95)', C.ink], [3.6, '▲ Left hand lost', C.warn, '#0b0b0b'], [5.0, '● Reacquired', C.ink, '#0b0b0b']]
      .map(([s, txt, b, fg]) => {
        const tg = makeTag(lcard.wrap, txt, b, fg, 26);
        const stem = el('div', lcard.wrap, 'abs', { width: '2px', background: b });
        return { s, tg, stem, u: solve(s) };
      });
    function update(t) {
      const on = t >= (TL.f1.wipe[0] + TL.f1.wipe[1]) / 2 && t < (TL.f2.wipe[0] + TL.f2.wipe[1]) / 2; vis(root, on); if (!on) return;
      const { press, release } = TL.f2;
      revealHeadline(head, t, 10.0);
      T(sub, { x: L.head.x, y: subY + (1 - E.outExpo(P(t, 10.2, 10.6))) * 30, o: P(t, 10.2, 10.4) });
      const ev = E.outExpo(P(t, 10.0, 10.4)), el2 = E.outExpo(P(t, 10.08, 10.5));
      placeCard(vcard, L.video.x + (1 - ev) * 220, L.video.y, kv, { o: P(t, 10.0, 10.1), ry: (1 - ev) * 25, blur: (1 - ev) * 10 });
      placeCard(lcard, L.lanes.x, L.lanes.y + (1 - el2) * 160, kl, { o: P(t, 10.08, 10.18), rx: (1 - el2) * -25, blur: (1 - el2) * 10 });
      let idx, f, u = 0;
      if (t < press) { idx = 0; f = -1; }
      else if (t < release) { u = P(t, press, release); f = 1 + u * 54; idx = 1 + Math.min(54, Math.floor(u * 54)); }
      else { idx = 56; f = 55; u = 1; }
      setSrc(vcard.img, UI + `f2/video_${pad(idx, 3)}.jpg`);
      setSrc(lcard.img, UI + `f2/lanes_${pad(idx, 3)}.jpg`);
      const cs = SQ.cursor.map((p, i) => ({ x: p.x, y: (i === 0 ? p.y : SQ.cursor[1].y) - CT }));
      let x, y;
      if (t < press) {
        const a = E.outCubic(P(t, 10.1, 10.38)), b = E.inOutCubic(P(t, 10.38, press));
        x = lerp(lerp(crop * 0.9, cs[0].x, a), cs[1].x, b); y = lerp(lerp(lr.h * 1.2, cs[0].y, a), cs[1].y, b);
      } else {
        const ff = clamp(f, 1, 55.999), i0 = Math.min(cs.length - 2, Math.floor(ff)), fr = ff - i0;
        x = lerp(cs[i0].x, cs[i0 + 1].x, fr); y = cs[1].y;
        const lv = E.inCubic(P(t, release + 0.2, release + 0.6));
        y += lv * 160; x += lv * 90;
      }
      setCursor(cu, x, y, kl, P(t, 10.1, 10.16) * (1 - P(t, release + 0.4, release + 0.55)), t >= press && t < release, [press, release], t);
      const sT = t < press ? 6.0 : scrubT(u);
      clock.textContent = `${pad(Math.floor(sT), 2)}.${pad(Math.floor((sT * 1000) % 1000), 3)} s`;
      const cy = L.clock.y;
      T(clockLbl, { x: L.clock.x, y: cy - 34, o: P(t, 10.3, 10.45) });
      T(clock, { x: L.clock.x, y: cy, o: P(t, 10.3, 10.4), s: 1 + 0.05 * decay(t, press, 0.1) });
      const tgSize = 26 / kl;
      const laneY = SQ.canvasOffset.y - CT + 14; // left-hand lane, card coords
      marks.forEach((m, i) => {
        const tm = press + m.u * (release - press);
        const pi = popIn(t, tm, 0.28);
        const xx = tx(m.s);
        m.tg.style.fontSize = tgSize + 'px';
        m.tg.style.transformOrigin = '0 100%';
        const level = i; // stacked so the three never collide
        const ty = -(52 + level * 50) / kl; // bottom of the tag, above the card
        T(m.tg, { x: xx - 6 / kl, y: ty - tgSize * 1.65, s: pi.s, o: pi.o });
        T(m.stem, { x: xx - 1 / kl, y: ty, o: pi.o * 0.9 });
        m.stem.style.height = (laneY - ty) + 'px';
        m.stem.style.width = (2 / kl) + 'px';
      });
    }
    return { update };
  })();

  // ================================================================ SCENE 5: F3 filter to problems, click, jump
  const f3 = (() => {
    const L = LAY.f3, SQ = MF.sequences.f3, st = SQ.states;
    const root = el('div', world, 'layer');
    const head = makeHeadline(root, L.head.oneLine ? [[['JUMP TO THE ', C.ink], ['PROBLEMS.', C.warn]]] : [[['JUMP TO', C.ink]], [['THE ', C.ink], ['PROBLEMS.', C.warn]]], L.head);
    const sub = makeSub(root, 'Filter: Problems only. Click an event to seek.', { size: IS_H ? 28 : 30 });
    const subY = head.y + head.h + 26;
    const er = st[0].rects.events;
    const ecard = makeCard(root, er.w, er.h, UI + 'f3/events_0_idle.png');
    const cu = makeCursor(ecard.wrap);
    const vr = st[0].rects.video, lr = st[0].rects.lanes;
    const vcard = makeCard(root, vr.w, vr.h, UI + 'f3/video_3_hover_event.jpg');
    const kv = L.video.w / vr.w;
    let lcard = null, kl = 1;
    if (L.lanes) { lcard = makeCard(root, L.lanes.crop, lr.h - 88, UI + 'f3/lanes_3_hover_event.jpg', { imgW: lr.w, imgH: lr.h }); lcard.img.style.top = '-88px'; kl = L.lanes.w / L.lanes.crop; }
    const lostTag = makeTag(vcard.wrap, '▲ 00:03.600 · Left hand lost', C.warn, '#0b0b0b', 30);
    let lost = null;
    if (L.lost) {
      const ls = Math.min(130, fitHead('▲ LOST', L.lost.w), fitHead('03.600 S', L.lost.w));
      lost = el('div', root, 'abs head', { fontSize: ls + 'px', color: C.warn, lineHeight: '0.95' }, '▲ LOST<br><span style="color:#f0efec">03.600<span style="text-transform:none"> s</span></span>');
    }
    const names = st.map(s => s.name);
    function update(t) {
      const on = t >= (TL.f2.wipe[0] + TL.f2.wipe[1]) / 2 && t < 16.02; vis(root, on); if (!on) return;
      const { clickFilter, hoverEvent, clickEvent } = TL.f3;
      revealHeadline(head, t, 13.0);
      T(sub, { x: L.head.x, y: subY + (1 - E.outExpo(P(t, 13.2, 13.6))) * 30, o: P(t, 13.2, 13.4) });
      // events card state
      let si = 0;
      if (t >= clickEvent) si = 4; else if (t >= hoverEvent) si = 3; else if (t >= clickFilter) si = 2; else if (t >= 13.33) si = 1;
      setSrc(ecard.img, UI + `f3/events_${names[si]}.png`);
      // layout: before the jump the events list is the hero; after, the evidence takes over
      const j = E.inOutCubic(P(t, clickEvent + 0.05, clickEvent + 0.4));
      const ek = lerp(L.ev0.k, L.ev1.k, j);
      const ein = E.outExpo(P(t, 13.0, 13.4));
      const listPop = 1 + 0.025 * decay(t, clickFilter, 0.09);
      placeCard(ecard, lerp(L.ev0.x, L.ev1.x, j), lerp(L.ev0.y, L.ev1.y, j) + (1 - ein) * 200, ek * listPop, { o: P(t, 13.0, 13.1), rx: (1 - ein) * -20, blur: (1 - ein) * 10 });
      // the filtered list refreshes with a quick lift
      ecard.img.style.transform = `translateY(${(t >= clickFilter ? (1 - E.outExpo(P(t, clickFilter, clickFilter + 0.2))) * 10 : 0)}px)`;
      // cursor path (rel coords in the events panel)
      const rel = st.map(s => s.rel);
      let x, y;
      if (t < 13.33) { const a = E.outCubic(P(t, 13.02, 13.33)); x = lerp(rel[0].x, rel[1].x, a); y = lerp(rel[0].y + 40, rel[1].y, a); }
      else if (t < 13.7) { x = rel[1].x; y = rel[1].y; }
      else if (t < hoverEvent) { const a = E.inOutCubic(P(t, 13.7, hoverEvent - 0.02)); x = lerp(rel[2].x, rel[3].x, a); y = lerp(rel[2].y, rel[3].y, a); }
      else { x = rel[3].x; y = rel[3].y; }
      setCursor(cu, x, y, ek, P(t, 13.02, 13.1) * (1 - P(t, clickEvent + 0.5, clickEvent + 0.65)),
        (t >= clickFilter && t < clickFilter + 0.08) || (t >= clickEvent && t < clickEvent + 0.08), [clickFilter, clickEvent], t);
      // evidence: video (and timeline) jump to 00:03.600
      const jumped = t >= clickEvent;
      setSrc(vcard.img, UI + `f3/video_${jumped ? '4_jumped' : '3_hover_event'}.jpg`);
      const push = E.inOutCubic(P(t, TL.f3.push[0], TL.f3.push[1]));
      let vo, vy = L.video.y, vk = kv;
      if (L.side) { const vi = E.outExpo(P(t, 13.15, 13.55)); vo = P(t, 13.15, 13.25); vy += (1 - vi) * 120; }
      else { const vi = E.outExpo(P(t, clickEvent, clickEvent + 0.4)); vo = P(t, clickEvent, clickEvent + 0.06); vy += (1 - vi) * 500; }
      const flashJ = decay(t, clickEvent, 0.15);
      placeCard(vcard, L.video.x, vy, vk, { o: vo });
      vcard.glow.style.boxShadow = `0 0 0 4px ${C.warn}, 0 0 50px ${C.warn}`;
      vcard.glow.style.opacity = jumped ? 0.95 * flashJ + 0.25 * (1 - P(t, clickEvent + 0.3, 15.5)) : 0;
      if (lcard) {
        setSrc(lcard.img, UI + `f3/lanes_${jumped ? '4_jumped' : '3_hover_event'}.jpg`);
        const li = E.outExpo(P(t, 13.25, 13.65));
        placeCard(lcard, L.lanes.x, L.lanes.y + (1 - li) * 120, kl, { o: P(t, 13.25, 13.35) });
      }
      const pt = popIn(t, clickEvent + 0.12, 0.3);
      lostTag.style.fontSize = (30 / vk) + 'px';
      lostTag.style.transformOrigin = '0 0';
      T(lostTag, { x: 22 / vk, y: vr.h - 80 / vk, s: pt.s, o: pt.o });
      if (lost) { const lp = popIn(t, clickEvent + 0.2, 0.32); T(lost, { x: L.lost.x, y: L.lost.y, s: lp.s, o: lp.o }); lost.style.transformOrigin = '0 0'; }
      // push in on the evidence, then collapse to the proof
      const [c0, c1] = TL.f3.collapse;
      const col = E.inExpo(P(t, c0, c1));
      const vc = { x: L.video.x + vr.w * vk / 2, y: L.video.y + vr.h * vk / 2 };
      const ps = 1 + 0.18 * push;
      const cs = ps * (1 - col * 0.96);
      root.style.transformOrigin = `${lerp(vc.x, W / 2, col)}px ${lerp(vc.y, H / 2, col)}px`;
      T(root, { s: cs, r: col * 8, o: 1 - P(t, c1 - 0.05, c1), blur: col * 12 });
    }
    return { update };
  })();

  // ================================================================ SCENE 6: METRIC + LOCKUP
  const metric = (() => {
    const L = LAY.metric;
    const root = el('div', world, 'layer');
    const numSize = 100 * L.num.maxW / textW('239', FAM.head, 700, 100, -0.04);
    const centred = L.num.cx !== 0;
    const cbox = centred ? { width: W + 'px', textAlign: 'center' } : {};
    const num = el('div', root, 'abs head', Object.assign({ fontSize: numSize + 'px', letterSpacing: '-0.04em', lineHeight: '0.82', fontVariantNumeric: 'tabular-nums', color: C.ink }, cbox), '000');
    const numW = textW('239', FAM.head, 700, numSize, -0.04);
    const lblSize = Math.min(IS_V ? 140 : 120, fitHead('✓ TESTS PASSED', L.label.maxW));
    const lbl = el('div', root, 'abs head', Object.assign({ fontSize: lblSize + 'px' }, cbox));
    const lblMask = el('div', lbl, 'mask'); const lblIn = el('div', lblMask, null, {}, `<span style="color:${C.good}">✓</span> TESTS PASSED`);
    const lblW = textW('✓ TESTS PASSED', FAM.head, 700, lblSize, -0.03, 'uppercase');
    const subSize = IS_H ? 32 : (IS_V ? 36 : 30);
    const sub = el('div', root, 'abs', Object.assign({ fontFamily: FAM.head, fontSize: subSize + 'px', color: C.ink2, whiteSpace: 'nowrap' }, cbox), '197 pipeline <span style="color:#898781">(1 skipped)</span> + 42/42 backend');
    const src = el('div', root, 'abs mono', Object.assign({ fontSize: (IS_H ? 20 : 22) + 'px', color: C.muted, letterSpacing: '0.08em', whiteSpace: 'nowrap' }, cbox), 'SOURCE: README · VERIFICATION 1 NOV 2026');
    const subW = textW('197 pipeline (1 skipped) + 42/42 backend', FAM.head, 400, subSize);
    // grid of 240 tests: 197 pipeline passed, 1 skipped, 42 backend passed
    const G = L.grid, rows = Math.ceil(240 / G.cols);
    const gw = G.cols * (G.cell + G.gap) - G.gap, gh = rows * (G.cell + G.gap) - G.gap;
    const gc = el('canvas', root, 'abs'); gc.width = gw + 40; gc.height = gh + 40;
    const gx = gc.getContext('2d');
    const isNumX = L.num.cx !== 0;
    const numX = isNumX ? 0 : L.num.x;
    const numY = L.num.y;
    const lblY = numY + numSize * 0.86 + (IS_V ? 40 : 24);
    const lblX = isNumX ? 0 : L.label.x;
    const subY2 = lblY + lblSize * 0.95 + 26;
    const subX = isNumX ? 0 : L.label.x;
    const srcY = IS_V ? 1790 : (IS_S ? 1020 : subY2 + 66);
    // ---- lockup
    const lk = el('div', world, 'layer');
    const wmText = 'MOTIONIQ';
    const wmSize = 100 * LAY.lockup.maxW / textW(wmText, FAM.ui, 700, 100, 0.06);
    const wmW = textW(wmText, FAM.ui, 700, wmSize, 0.06);
    const wm = el('div', lk, 'abs', { fontFamily: FAM.ui, fontWeight: 700, fontSize: wmSize + 'px', letterSpacing: '0.06em', lineHeight: '1', whiteSpace: 'nowrap' });
    const letters = [...wmText].map(ch => el('span', wm, null, { display: 'inline-block', transformOrigin: '50% 60%' }, ch));
    const wmX = (W - wmW) / 2, wmY = H * LAY.lockup.cy - wmSize * 0.5;
    const tagSize = IS_H ? 54 : (IS_V ? 58 : 50);
    const tagline = el('div', lk, 'abs', { fontFamily: FAM.head, fontSize: tagSize + 'px', color: C.ink, whiteSpace: 'nowrap' }, 'Find the usable seconds.');
    const tagW = textW('Find the usable seconds.', FAM.head, 400, tagSize);
    const bL = el('div', lk, 'abs', { height: '12px', width: '10px', background: C.left });
    const bR = el('div', lk, 'abs', { height: '12px', width: '10px', background: C.right });
    const kick = el('div', lk, 'abs mono', { fontSize: (IS_H ? 24 : 26) + 'px', letterSpacing: '0.34em', color: C.ink2, width: W + 'px', textAlign: 'center' }, 'BIOS · SHIP HAPPENS');
    const foot = el('div', lk, 'abs mono', { fontSize: (IS_H ? 22 : 24) + 'px', letterSpacing: '0.06em', color: C.muted, width: W + 'px', textAlign: 'center' }, 'github.com/UdaiBatta/BIOS---Ship-Happens');
    const foot2 = el('div', lk, 'abs mono', { fontSize: (IS_H ? 20 : 22) + 'px', letterSpacing: '0.2em', color: C.muted, width: W + 'px', textAlign: 'center' }, 'PS4 · 3D HAND MOTION · OFFLINE · CPU');
    const value = t => Math.round(239 * E.outCubic(P(t, TL.metric.countStart, TL.metric.lock)));
    function drawGrid(t, lit) {
      gx.clearRect(0, 0, gc.width, gc.height);
      gx.textAlign = 'center'; gx.textBaseline = 'middle';
      gx.font = `700 ${Math.round(G.cell * 0.62)}px ${FAM.head}`;
      // order: 197 passed, 1 skipped, 42 backend passed
      let passedSoFar = 0;
      for (let i = 0; i < 240; i++) {
        const skipped = i === 197;
        if (!skipped) passedSoFar++;
        const on = skipped ? lit >= 197 : passedSoFar <= lit;
        const cx = 20 + (i % G.cols) * (G.cell + G.gap) + G.cell / 2, cy = 20 + Math.floor(i / G.cols) * (G.cell + G.gap) + G.cell / 2;
        const sz = G.cell * (on ? 1 : 0.5);
        gx.fillStyle = on ? (skipped ? '#3a3a37' : C.good) : 'rgba(255,255,255,0.05)';
        const r = 6, x0 = cx - sz / 2, y0 = cy - sz / 2;
        gx.beginPath(); gx.roundRect(x0, y0, sz, sz, r); gx.fill();
        if (on) { gx.fillStyle = skipped ? C.muted : '#ffffff'; gx.fillText(skipped ? '–' : '✓', cx, cy + 1); }
      }
    }
    function update(t) {
      const on = t >= 15.95 && t < 18.1; vis(root, on);
      const lon = t >= 17.95; vis(lk, lon);
      const { countStart, lock, lockup } = TL.metric;
      if (on) {
        const v = value(t);
        num.textContent = pad(v, 3);
        const ni = E.outExpo(P(t, countStart, countStart + 0.3));
        const lockPunch = decay(t, lock, 0.12);
        const col = E.inExpo(P(t, TL.metric.collapse[0], TL.metric.collapse[1]));
        T(num, { x: numX, y: numY + (1 - ni) * 80, s: 1 + 0.08 * lockPunch, o: P(t, countStart, countStart + 0.05), blur: (t < lock ? 2.5 * (1 - P(t, countStart + 0.5, lock)) : 0) });
        num.style.color = t >= lock ? C.ink : C.ink2;
        const lu = E.outExpo(P(t, lock, lock + 0.4));
        T(lbl, { x: lblX, y: lblY, o: t >= lock ? 1 : 0 });
        T(lblIn, { y: (1 - lu) * lblSize * 1.05 });
        T(sub, { x: subX, y: subY2 + (1 - E.outExpo(P(t, lock + 0.125, lock + 0.5))) * 24, o: P(t, lock + 0.125, lock + 0.3) });
        T(src, { x: isNumX ? 0 : L.label.x, y: srcY, o: P(t, lock + 0.25, lock + 0.45) });
        drawGrid(t, v);
        const gi = E.outExpo(P(t, countStart, countStart + 0.35));
        T(gc, { x: G.x - 20, y: G.y - 20 + (1 - gi) * 60, o: P(t, countStart, countStart + 0.1) });
        root.style.transformOrigin = `${W / 2}px ${H / 2}px`;
        T(root, { s: 1 - 0.9 * col, o: 1 - col, blur: col * 14 });
      }
      if (lon) {
        letters.forEach((s, i) => {
          const t0 = lockup + i * 0.022;
          const u = P(t, t0, t0 + 0.34), e = E.outExpo(u), dir = i % 2 ? 1 : -1;
          T(s, { y: dir * (1 - e) * wmSize, s: lerp(2.0, 1, e), r: dir * (1 - e) * 12, o: P(t, t0, t0 + 0.04), blur: 18 * (1 - E.outCubic(P(t, t0, t0 + 0.16))) });
        });
        const pushS = 1 + 0.045 * P(t, lockup, 20);
        lk.style.transformOrigin = `${W / 2}px ${H / 2}px`;
        const fo = 1 - P(t, TL.metric.fadeOut[0], TL.metric.fadeOut[1]);
        T(lk, { s: pushS, o: fo });
        T(wm, { x: wmX, y: wmY });
        const bu = E.outExpo(P(t, lockup + 0.1, lockup + 0.5));
        const by = wmY + wmSize * 1.08, half = wmW / 2;
        T(bL, { x: W / 2 - half * bu, y: by, sx: Math.max(0.01, half * bu - 8) / 10, o: 1 });
        T(bR, { x: W / 2 + 8, y: by, sx: Math.max(0.01, half * bu - 8) / 10, o: 1 });
        const tu = E.outExpo(P(t, lockup + 0.25, lockup + 0.7));
        T(tagline, { x: (W - tagW) / 2, y: by + 50 + (1 - tu) * 30, o: P(t, lockup + 0.25, lockup + 0.4), blur: (1 - tu) * 6 });
        T(kick, { y: wmY - (IS_V ? 80 : 70), o: P(t, lockup + 0.375, lockup + 0.6) });
        const fy = IS_V ? H - 150 : H - (IS_S ? 110 : 100);
        T(foot, { y: fy, o: P(t, lockup + 0.5, lockup + 0.75) });
        T(foot2, { y: fy + 40, o: P(t, lockup + 0.6, lockup + 0.85) });
      }
    }
    return { update };
  })();

  // ================================================================ HUD
  const hudLbl = el('div', hud, 'abs mono', { fontSize: (IS_H ? 20 : 22) + 'px', letterSpacing: '0.18em', color: C.ink2, whiteSpace: 'nowrap' });
  const hudTc = el('div', hud, 'abs mono', { fontSize: (IS_H ? 20 : 22) + 'px', letterSpacing: '0.12em', color: C.muted, whiteSpace: 'nowrap', textAlign: 'right', width: '400px' });
  const hudCap = el('div', hud, 'abs mono', { fontSize: (IS_H ? 18 : 20) + 'px', letterSpacing: '0.06em', color: C.muted, whiteSpace: 'nowrap' }, 'MOTIONIQ viewer prototype · synthetic demo data');
  const hudBar = el('div', hud, 'abs', { height: '3px', width: W + 'px', background: 'rgba(255,255,255,0.08)' });
  const hudFill = el('div', hudBar, 'abs', { height: '3px', width: W + 'px', background: C.left, transformOrigin: '0 0' });
  function updateHud(t) {
    const sec = TL.sections.find(s => t >= s.t0 && t < s.t1) || TL.sections[TL.sections.length - 1];
    const sw = P(t, sec.t0, sec.t0 + 0.2);
    hudLbl.innerHTML = `<span style="color:${C.left}">■</span> ${sec.label}`;
    const hy = IS_V ? 76 : 44;
    const end = 1 - P(t, TL.metric.lockup - 0.1, TL.metric.lockup);
    T(hudLbl, { x: M, y: hy + (1 - E.outExpo(sw)) * -20, o: Math.min(E.outExpo(sw) + (sec.t0 === 0 ? 1 : 0), 1) * end * P(t, 0.15, 0.3) });
    hudTc.textContent = `${tc(t).slice(1)}  ·  120 BPM`;
    T(hudTc, { x: W - M - 400, y: hy, o: end * P(t, 0.15, 0.3) });
    T(hudCap, { x: M, y: H - (IS_V ? 96 : 52), o: P(t, 4.5, 4.8) * (1 - P(t, 15.6, 15.9)) });
    hudFill.style.background = t < 7 ? C.left : (t < 13 ? C.right : C.left);
    T(hudFill, { sx: t / TL.duration });
    T(hudBar, { y: H - 3, o: end });
  }

  // ================================================================ FX: wipes, flashes
  const flashes = [[TL.drop, '#ffffff', 0.85, 0.12], [7.0, '#ffffff', 0.35, 0.1], [TL.metric.lock, '#ffffff', 0.35, 0.1], [TL.metric.lockup, '#ffffff', 0.8, 0.14], [16.0, C.warn, 0.25, 0.1]];
  function drawFx(t) {
    fxx.setTransform(1, 0, 0, 1, 0, 0);
    fxx.clearRect(0, 0, W, H);
    // lane wipe (wearer-left / wearer-right / other people, like the timeline lanes) F1 -> F2
    const [w0, w1] = TL.f1.wipe; const wm = (w0 + w1) / 2;
    if (t >= w0 && t <= w1) {
      const cols = [C.left, C.right, '#898781', C.left, C.right];
      const n = IS_V ? 5 : 3, bh = H / n;
      for (let i = 0; i < n; i++) {
        const d = i * 0.03;
        const a = E.inCubic(P(t, w0 + d, wm)), b = E.outCubic(P(t, wm + d * 0.5, w1));
        const xr = a * W * 1.05, xl = b * W * 1.05;
        fxx.fillStyle = cols[i % cols.length];
        fxx.fillRect(xl, i * bh - 1, Math.max(0, xr - xl), bh + 2);
      }
    }
    // hazard wipe (warning yellow) F2 -> F3
    const [h0, h1] = TL.f2.wipe; const hm = (h0 + h1) / 2;
    if (t >= h0 && t <= h1) {
      const a = E.inCubic(P(t, h0, hm)), b = E.outCubic(P(t, hm, h1));
      const span = W + H * 0.5;
      fxx.save();
      fxx.beginPath();
      const x1 = -H * 0.25 + a * span * 1.1, x0 = -H * 0.25 + b * span * 1.1;
      fxx.moveTo(x0 - H * 0.25, H); fxx.lineTo(x0 + H * 0.25, 0); fxx.lineTo(x1 + H * 0.25, 0); fxx.lineTo(x1 - H * 0.25, H); fxx.closePath();
      fxx.fillStyle = C.warn; fxx.fill(); fxx.clip();
      fxx.fillStyle = 'rgba(11,11,11,0.9)';
      const st = 90;
      for (let s = -H; s < W + H; s += st * 2) {
        fxx.beginPath(); fxx.moveTo(s, H); fxx.lineTo(s + H * 0.5, 0); fxx.lineTo(s + H * 0.5 + st * 0.45, 0); fxx.lineTo(s + st * 0.45, H); fxx.closePath(); fxx.fill();
      }
      fxx.restore();
    }
    // ring burst at the proof
    if (t >= 15.92 && t < 16.6) {
      const u = P(t, 15.92, 16.6);
      fxx.strokeStyle = `rgba(250,178,25,${(1 - u) * 0.9})`;
      fxx.lineWidth = 10 * (1 - u) + 1;
      fxx.beginPath(); fxx.arc(W / 2, H / 2, E.outExpo(u) * Math.max(W, H) * 0.7, 0, Math.PI * 2); fxx.stroke();
    }
    // flashes
    for (const [ti, col, a, tau] of flashes) {
      const d = decay(t, ti, tau) * a;
      if (d > 0.004) { fxx.globalAlpha = d; fxx.fillStyle = col; fxx.fillRect(0, 0, W, H); fxx.globalAlpha = 1; }
    }
    // end fade to black
    const fo = P(t, TL.metric.fadeOut[0], TL.metric.fadeOut[1]);
    if (fo > 0) { fxx.globalAlpha = fo; fxx.fillStyle = '#000'; fxx.fillRect(0, 0, W, H); fxx.globalAlpha = 1; }
  }

  // ================================================================ seek
  const scenes = [hook, product, f1, f2, f3, metric];
  window.ready = (async () => {
    await document.fonts.ready;
    // warm fonts used in canvas
    textW('x', FAM.head, 700, 20); textW('x', FAM.ui, 700, 20); textW('x', FAM.mono, 400, 20);
    hook.measure();
    await Promise.all(pending.splice(0));
    return { W, H, FMT };
  })();
  window.seek = async (t) => {
    drawBg(t);
    const c = camera(t);
    T(cam, { x: c.x, y: c.y, r: c.r, s: c.s });
    for (const s of scenes) s.update(t);
    updateHud(t);
    drawFx(t);
    const gi = Math.floor(t * 30) % 6;
    grain.style.backgroundImage = `url(grain_${gi}.png)`;
    grain.style.backgroundPosition = `${Math.floor(hash(t * 60) * 384)}px ${Math.floor(hash(t * 60 + 5) * 384)}px`;
    await Promise.all(pending.splice(0));
    return true;
  };
})();
