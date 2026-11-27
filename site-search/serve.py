"""簡易検索HTTP API。usage: python serve.py [port] -> /search?q=..."""

import json
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

DB_PATH = "index.db"


def do_search(query: str, limit: int = 10):
    conn = sqlite3.connect(DB_PATH)
    fts_query = " ".join(f'"{t}"' for t in query.split())
    try:
        rows = conn.execute(
            """
            SELECT p.url, p.title, snippet(pages_fts, 1, '«', '»', '…', 20)
            FROM pages_fts f JOIN pages p ON p.url = f.url
            WHERE pages_fts MATCH ? ORDER BY rank LIMIT ?
            """,
            (fts_query, limit),
        ).fetchall()
    except sqlite3.OperationalError:
        rows = []
    finally:
        conn.close()
    return [
        {"url": u, "title": t, "snippet": s} for u, t, s in rows
    ]


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parts = urlsplit(self.path)
        if parts.path != "/search":
            self.send_error(404)
            return
        q = parse_qs(parts.query).get("q", [""])[0]
        limit = int(parse_qs(parts.query).get("limit", ["10"])[0])
        body = json.dumps(
            {"query": q, "results": do_search(q, limit) if q else []},
            ensure_ascii=False,
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    import sys

    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    print(f"http://127.0.0.1:{port}/search?q=検索語")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
