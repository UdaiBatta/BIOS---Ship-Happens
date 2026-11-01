// Usage:
//   node scripts/render.js stills <fmt> <outDir> t1 t2 ...      -> PNG stills at given times
//   node scripts/render.js video  <fmt> <out.mp4> [fps] [sub]   -> frames piped to ffmpeg (sub = motion-blur subframes)
const { chromium } = require('playwright');
const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

const [mode, fmt, out, ...rest] = process.argv.slice(2);
const SIZES = { '9x16': [1080, 1920], '1x1': [1080, 1080], '16x9': [1920, 1080] };
const [W, H] = SIZES[fmt];
const COMP = 'file://' + path.resolve(__dirname, '../comp/index.html') + '?fmt=' + fmt;

(async () => {
  const b = await chromium.launch({ args: ['--disable-gpu-vsync', '--force-color-profile=srgb'] });
  const p = await b.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 1 });
  const errs = [];
  p.on('pageerror', e => errs.push(e.message));
  p.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
  await p.goto(COMP);
  await p.evaluate(() => window.ready);
  if (errs.length) { console.error('PAGE ERRORS', errs); }
  if (mode === 'stills') {
    fs.mkdirSync(out, { recursive: true });
    for (const ts of rest) {
      const t = parseFloat(ts);
      await p.evaluate(t => window.seek(t), t);
      await p.screenshot({ path: path.join(out, `${fmt}_${t.toFixed(3)}.png`) });
    }
  } else {
    const fps = parseInt(rest[0] || '60', 10), sub = parseInt(rest[1] || '1', 10);
    const dur = 20.0, N = Math.round(dur * fps);
    const rfps = fps * sub;
    // sub>1: render sub-frames and average them in ffmpeg (tmix) for real motion blur
    const vf = sub > 1 ? ['-vf', `tmix=frames=${sub}:weights='${Array(sub).fill(1).join(' ')}',select='eq(mod(n\\,${sub})\\,${sub - 1})',setpts=N/(${fps}*TB)`] : [];
    const ff = spawn('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', String(rfps), '-c:v', 'mjpeg', '-i', '-',
      ...vf, '-r', String(fps), '-c:v', 'libx264', '-preset', 'medium', '-crf', '16', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', out],
      { stdio: ['pipe', 'inherit', 'inherit'] });
    const t0 = Date.now();
    const total = N * sub;
    for (let i = 0; i < total; i++) {
      // sub-frames are spread over a 180-degree shutter centred on the frame time
      const f = Math.floor(i / sub), s = i % sub;
      const t = Math.max(0, (f + (sub > 1 ? (s / sub - 0.5) * 0.5 : 0)) / fps);
      await p.evaluate(t => window.seek(t), t);
      const buf = await p.screenshot({ type: 'jpeg', quality: 94 });
      if (!ff.stdin.write(buf)) await new Promise(r => ff.stdin.once('drain', r));
      if (i % 120 === 0) process.stdout.write(`\r${fmt} ${i}/${total} ${((Date.now() - t0) / 1000).toFixed(0)}s   `);
    }
    ff.stdin.end();
    await new Promise(r => ff.on('close', r));
    console.log(`\n${fmt} done in ${((Date.now() - t0) / 1000).toFixed(0)}s`);
  }
  if (errs.length) console.error('PAGE ERRORS', errs.slice(0, 5));
  await b.close();
})();
