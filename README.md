# For Personal Use

自分用に使うためのツール集です。各ツールは個人的な用途のために作られたもので、汎用的な品質・サポートは想定していません(as-is 提供です)。

## Contents

| ツール | 説明 |
|---|---|
| [site-search](./site-search) | Google CSE 等に依存しない、特定 URL/ドメイン限定の自前検索システム。クローラーで SQLite FTS5 に索引付けし、CLI / HTTP API で全文検索できる |
| [urlshot](./urlshot) | URL を入力すると Playwright でスクリーンショットを撮って表示するプレビューツール。実サイトの iframe 読み込みは行わず、画像のみの安全な設計 |
| [video-app](./video-app) | OfflineTube — 動画を閲覧するための単一 HTML アプリ |

## 使い方

各ツールの詳細はそれぞれのフォルダー(および README)を参照してください。

- **site-search** — Python 製。`python crawler.py <URL>` で索引化 → `python search.py "キーワード"` で検索
- **urlshot** — Node.js 製。`npm install` 後 `node server.js` で起動し、`http://localhost:3000` でURLを入力
- **video-app** — `index.html` をブラウザで開くだけ

## Notes

- 個人利用前提のため、環境に依存する設定やパスが含まれている可能性があります
- 不具合があれば自分で直して使うことを前提としています
