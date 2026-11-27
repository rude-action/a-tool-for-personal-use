"""全文検索 CLI。
usage:
  python search.py "クエリ"                       # 全体検索
  python search.py "クエリ" --url "https://raw.githubusercontent.com/user/*"
"""

import argparse
import fnmatch
import sqlite3

DB_PATH = "index.db"


def search(query: str, limit: int = 10, url_pattern: str | None = None):
    conn = sqlite3.connect(DB_PATH)
    fts_query = " ".join(f'"{t}"' for t in query.split())
    sql = """
        SELECT p.url, p.title, snippet(pages_fts, 1, '«', '»', '…', 20)
        FROM pages_fts f JOIN pages p ON p.url = f.url
        WHERE pages_fts MATCH ?
        ORDER BY rank
    """
    try:
        rows = conn.execute(sql, (fts_query,)).fetchall()
    except sqlite3.OperationalError as e:
        print(f"検索エラー: {e}")
        return []
    finally:
        conn.close()
    if url_pattern:
        rows = [r for r in rows if fnmatch.fnmatchcase(r[0], url_pattern)]
    rows = rows[:limit]
    for i, (url, title, snip) in enumerate(rows, 1):
        print(f"{i}. {title or '(無題)'}\n   {url}\n   {snip}\n")
    return rows


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--url", help="URL globパターンで結果を絞り込み")
    args = ap.parse_args()
    search(args.query, args.limit, args.url)
