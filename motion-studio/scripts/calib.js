const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1600, height: 1320 }, deviceScaleFactor: 1 });
  await p.goto('file://' + require('path').resolve(__dirname, '../../frontend/prototype/index.html'));
  await p.waitForTimeout(800);
  const c = await p.locator('#cvLanes').boundingBox(); console.log('lanes', c);
  for (const x of [200, 400, 800, 1100]) {
    await p.mouse.click(c.x + x, c.y + 20); await p.waitForTimeout(100);
    console.log(x, await p.locator('#timeInfo').innerText());
  }
  console.log(await p.evaluate(()=>getComputedStyle(document.querySelector('.ev')).cssText.length));
  const css = await p.evaluate(()=>[...document.styleSheets[0].cssRules].map(r=>r.cssText).filter(t=>/\.ev|hover|current/.test(t)).join('\n'));
  console.log(css);
  await b.close();
})();
