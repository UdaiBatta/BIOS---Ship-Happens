const { chromium } = require('playwright');
const fs = require('fs');
(async () => {
  const b = await chromium.launch();
  const m = JSON.parse(fs.readFileSync('assets/ui/manifest.json'));
  for (const [name, w, h] of [['L', 1600, 1320], ['P', 1080, 1740]]) {
    const p = await b.newPage({ viewport: { width: w, height: h } });
    await p.goto('file://' + require('path').resolve(__dirname, '../../frontend/prototype/index.html'));
    await p.waitForTimeout(600);
    const r = await p.locator('.brand').boundingBox();
    const cs = await p.evaluate(() => { const s = getComputedStyle(document.querySelector('.brand')); return { font: s.fontFamily, size: s.fontSize, weight: s.fontWeight, ls: s.letterSpacing }; });
    m.layouts[name].brand = { x: r.x, y: r.y, w: r.width, h: r.height, ...cs };
    console.log(name, m.layouts[name].brand);
    await p.close();
  }
  fs.writeFileSync('assets/ui/manifest.json', JSON.stringify(m, null, 2));
  await b.close();
})();
