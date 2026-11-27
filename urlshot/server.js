const express = require('express');
const { chromium } = require('playwright');

const app = express();
app.use(express.json());
app.use(express.static(__dirname + '/public'));
app.use('/shots', express.static(__dirname + '/shots'));

async function capture(url, width) {
  if (!/^https?:\/\//i.test(url)) url = 'https://' + url;

  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width, height: 800 } });
  const response = await page.goto(url, { waitUntil: 'networkidle', timeout: 60000 })
    .catch(() => page.goto(url, { waitUntil: 'load', timeout: 60000 }));
  await page.waitForTimeout(1500);

  const headers = response?.headers() || {};
  const xfo = (headers['x-frame-options'] || '').toLowerCase();
  const csp = (headers['content-security-policy'] || '').toLowerCase();
  const frameable =
    !xfo.includes('deny') && !xfo.includes('sameorigin') &&
    !csp.includes('frame-ancestors') && !csp.includes('frame-src');

  // 全ページ高さを取得（iframe を同じ高さで描画するために使う）
  const height = await page.evaluate(() =>
    Math.max(document.documentElement.scrollHeight, document.body?.scrollHeight || 0)
  );

  const image = `shots/${Date.now()}.png`;
  await page.screenshot({ path: image, fullPage: true });
  await browser.close();

  return { url, frameable, height, width, image: '/' + image };
}

app.post('/api/shot', async (req, res) => {
  const { url, width } = req.body || {};
  if (!url) return res.status(400).json({ error: 'URLが必要です' });
  try {
    res.json(await capture(url, parseInt(width, 10) || 1280));
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

const port = process.env.PORT || 3000;
app.listen(port, () => console.log(`http://localhost:${port} を開いてURLを入力してください`));
