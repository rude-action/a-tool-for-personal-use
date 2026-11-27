const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

async function takeScreenshot(url, { out, width = 1280, fullPage = true, waitMs = 1500 } = {}) {
  if (!/^https?:\/\//i.test(url)) url = 'https://' + url;

  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width, height: 800 } });
  await page.goto(url, { waitUntil: 'networkidle', timeout: 60000 }).catch(async () => {
    // networkidle はタイムアウトしやすいので load で再試行
    await page.goto(url, { waitUntil: 'load', timeout: 60000 });
  });
  await page.waitForTimeout(waitMs);

  fs.mkdirSync(path.dirname(out), { recursive: true });
  await page.screenshot({ path: out, fullPage });
  await browser.close();
  return out;
}

module.exports = { takeScreenshot };

if (require.main === module) {
  const args = process.argv.slice(2);
  if (args.length === 0) {
    console.log('使い方: node shot.js <URL> [出力.png] [--width 1280] [--viewport]');
    process.exit(1);
  }
  const url = args[0];
  const widthIdx = args.indexOf('--width');
  const width = widthIdx > -1 ? parseInt(args[widthIdx + 1], 10) : 1280;
  const fullPage = !args.includes('--viewport');
  const outArg = args[1] && !args[1].startsWith('--') ? args[1] : null;
  const out = outArg || path.join(__dirname, 'shots', `${url.replace(/^https?:\/\//, '').replace(/[^\w.-]+/g, '_')}-${Date.now()}.png`);

  takeScreenshot(url, { out, width, fullPage })
    .then((file) => console.log('保存しました: ' + file))
    .catch((e) => { console.error('エラー: ' + e.message); process.exit(1); });
}
