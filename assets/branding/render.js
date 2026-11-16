const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch(); const p = await b.newPage({viewport:{width:800,height:800}, deviceScaleFactor:1});
  await p.goto('file://' + process.argv[2]); await p.evaluate(() => document.fonts.ready); await p.waitForTimeout(800);
  for (const id of ['a','b','c']) await (await p.$('#'+id)).screenshot({path: `${process.argv[3]}/profile-${id}.png`});
  await b.close();
})();
