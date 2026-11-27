# Site-Scoped Search System

Google CSE 等に依存しない、特定URL/ドメイン限定の自前検索システム。

- `crawler.py` : 指定ドメイン配下をクロールし、本文テキストを SQLite FTS5 に索引付け
- `search.py` : 全文検索 CLI
- `serve.py` : 簡易 HTTP 検索 API (JSON)

## 使い方

```bash
python crawler.py https://example.com --max-pages 200
python crawler.py --repo user/repo --max-pages 100   # GitHubリポジトリ全体
python crawler.py --github-search "キーワード"       # GitHub検索で一致したリポジトリのREADMEを索引化
python search.py "検索語"
python serve.py 8080   # http://127.0.0.1:8080/search?q=...
```
