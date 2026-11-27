"""URLパターン(glob)で指定した範囲だけを取得・索引化するクローラー。

- シードに glob パターン (https://raw.githubusercontent.com/user/repo/main/*.md 等) を指定可能
- --url-file でURLリスト(1行1URL)を与えると、パターンに一致するものだけ取得
- HTML は本文抽出、text/plain はそのまま本文として索引化

依存: Python 標準ライブラリのみ
"""

import argparse
import fnmatch
import hashlib
import json
import os
import html.parser
import re
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
from collections import deque

DB_PATH = "index.db"
USER_AGENT = "SiteScopedSearchBot/1.0"
DELAY_SEC = 1.0
MAX_DEPTH = 5
SKIP_TAGS = {"script", "style", "noscript", "header", "footer", "nav", "svg"}


class TextExtractor(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text_parts = []
        self.links = []
        self.title = ""
        self._skip_depth = 0
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in SKIP_TAGS:
            self._skip_depth += 1
        elif tag == "title":
            self._in_title = True
        elif tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)

    def handle_endtag(self, tag):
        if tag in SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
        elif tag == "title":
            self._in_title = False
        elif not self._skip_depth and tag in {"p", "div", "li", "br", "h1", "h2", "h3"}:
            self.text_parts.append("\n")

    def handle_data(self, data):
        if self._skip_depth:
            return
        if self._in_title:
            self.title += data
        else:
            self.text_parts.append(data)

    def result(self):
        text = re.sub(r"\s+", " ", " ".join(self.text_parts)).strip()
        return self.title.strip(), text


def normalize(url: str, base: str = None) -> str | None:
    abs_url = urllib.parse.urljoin(base or url, url)
    p = urllib.parse.urlsplit(abs_url)
    if p.scheme not in ("http", "https"):
        return None
    return urllib.parse.urlunsplit((p.scheme, p.netloc, p.path, p.query, ""))


def matches_any(url: str, patterns: list[str]) -> bool:
    """URL がいずれかの glob パターンに一致するか。"""
    return any(fnmatch.fnmatchcase(url, pat) for pat in patterns)


def fetch(url: str):
    """(kind, title, text) を返す。kind は 'html' or 'text'。"""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            ctype = resp.headers.get("Content-Type", "")
            raw = resp.read()
    except Exception as e:
        print(f"  ! fetch error {url}: {e}", file=sys.stderr)
        return None
    charset = "utf-8"
    m = re.search(r"charset=([\w-]+)", ctype)
    if m:
        charset = m.group(1)
    body = raw.decode(charset, errors="replace")

    if "text/html" in ctype:
        parser = TextExtractor()
        try:
            parser.feed(body)
        except html.parser.HTMLParseError:
            return None
        title, text = parser.result()
        return "html", title, text, parser.links
    # text/plain, markdown, json などはそのまま本文扱い
    return "text", url.rsplit("/", 1)[-1], body, []


def init_db(conn: sqlite3.Connection):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS pages (
            url TEXT PRIMARY KEY,
            title TEXT,
            content TEXT,
            content_hash TEXT,
            fetched_at TEXT
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS pages_fts USING fts5(
            title, content, url, tokenize='trigram'
        );
        """
    )


def upsert(conn: sqlite3.Connection, url: str, title: str, text: str):
    h = hashlib.sha256(text.encode()).hexdigest()
    row = conn.execute(
        "SELECT content_hash FROM pages WHERE url=?", (url,)
    ).fetchone()
    if row and row[0] == h:
        return False
    if row:
        conn.execute("DELETE FROM pages WHERE url=?", (url,))
        conn.execute("DELETE FROM pages_fts WHERE url=?", (url,))
    conn.execute(
        "INSERT INTO pages VALUES (?,?,?,?,datetime('now'))", (url, title, text, h)
    )
    conn.execute(
        "INSERT INTO pages_fts(title, content, url) VALUES (?,?,?)", (title, text, url)
    )
    return True


TEXT_EXTS = {
    ".md", ".markdown", ".txt", ".rst", ".html", ".htm", ".css", ".js",
    ".mjs", ".ts", ".jsx", ".tsx", ".py", ".rb", ".go", ".rs", ".java",
    ".c", ".h", ".cpp", ".cs", ".php", ".sh", ".yml", ".yaml", ".toml",
    ".ini", ".cfg", ".sql", ".json", ".xml", ".svg",
}


def repo_file_urls(repo: str, branch: str = None) -> list[str]:
    """GitHub API でリポジトリ全体のファイル一覧を取得し、
    テキスト系ファイルの raw URL リストを返す。"""
    if branch is None:
        with urllib.request.urlopen(
            f"https://api.github.com/repos/{repo}", timeout=15
        ) as resp:
            branch = json.load(resp)["default_branch"]
    api = (
        f"https://api.github.com/repos/{repo}/git/trees/{branch}"
        "?recursive=1"
    )
    req = urllib.request.Request(api, headers={"Accept": "application/vnd.github+json",
                                               "User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        tree = json.load(resp)
    if tree.get("truncated"):
        print("! リポジトリが大きすぎてファイル一覧が打ち切られました", file=sys.stderr)
    urls = []
    for item in tree.get("tree", []):
        if item["type"] != "blob":
            continue
        path = item["path"]
        if os.path.splitext(path)[1].lower() not in TEXT_EXTS:
            continue
        if path.split("/")[0] in {"node_modules", "dist", "vendor", ".git"}:
            continue
        urls.append(f"https://raw.githubusercontent.com/{repo}/{branch}/{path}")
    return urls


def github_search_repos(query: str, top: int = 20) -> list[str]:
    """GitHub Search API でキーワードに一致するリポジトリを検索し、
    'owner/repo' 名のリスト (上位 top 件) を返す。"""
    api = "https://api.github.com/search/repositories?" + urllib.parse.urlencode(
        {"q": query, "sort": "stars", "per_page": min(top, 100)}
    )
    req = urllib.request.Request(api, headers={"Accept": "application/vnd.github+json",
                                               "User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)
    return [r["full_name"] for r in data.get("items", [])[:top]]


def crawl(patterns: list[str], url_file: str | None, max_pages: int,
          repo: str = None, branch: str = None, gh_search: str = None):
    patterns = [p for p in (patterns or []) if p]
    conn = sqlite3.connect(DB_PATH)
    init_db(conn)

    queue: deque[tuple[str, int]] = deque()
    seen: set[str] = set()

    # URL候補の収集: ファイル由来の明示URL + パターンが具体URLなら直接
    candidates: list[str] = []
    if gh_search:
        repos = github_search_repos(gh_search, max_pages)
        print(f"GitHub検索 '{gh_search}': {len(repos)} リポジトリ")
        for full in repos:
            candidates += [
                f"https://raw.githubusercontent.com/{full}/HEAD/README.md",
                f"https://raw.githubusercontent.com/{full}/HEAD/README.markdown",
            ]
    if repo:
        candidates += repo_file_urls(repo, branch)
    if url_file:
        with open(url_file, encoding="utf-8") as f:
            candidates += [line.strip() for line in f if line.strip()]
    candidates += [p for p in patterns if "*" not in p and "?" not in p]
    for u in candidates:
        u = normalize(u)
        if u and u not in seen:
            seen.add(u)
            queue.append((u, 0))
    # パターンに具体URLが含まれない場合、最初の具体URLをシードにリンク探索
    if not queue:
        seed = patterns[0].split("*")[0].rstrip("/") or "https://" + urllib.parse.urlsplit(patterns[0]).netloc
        seed = normalize(seed)
        if seed:
            seen.add(seed)
            queue.append((seed, 0))

    count = 0
    indexed_prefixes: set[str] = set()  # gh_search由来: README.md成功済みのリポジトリ
    while queue and count < max_pages:
        url, depth = queue.popleft()
        # パターン外のURLは索引化しない(シード起点のみ通過)
        if depth > 0 and not matches_any(url, patterns):
            continue
        # README.md が成功済みのリポジトリは README.markdown を試さない
        if url.endswith("/README.markdown") and url[: -len("/README.markdown")] in indexed_prefixes:
            continue
        print(f"[{count+1}/{max_pages}] {url}")
        result = fetch(url)
        time.sleep(DELAY_SEC)
        if not result:
            continue
        kind, title, text, links = result
        if url.endswith("/README.md"):
            indexed_prefixes.add(url[: -len("/README.md")])
        if text and upsert(conn, url, title, text):
            count += 1
            conn.commit()
        # HTML の場合のみ、パターンに一致するリンクを追加 (text はリンクを持たない)
        if kind == "html" and depth < MAX_DEPTH:
            for link in links:
                norm = normalize(link, url)
                if norm and norm not in seen and matches_any(norm, patterns):
                    seen.add(norm)
                    queue.append((norm, depth + 1))

    conn.close()
    print(f"\n完了: {count} ページを索引化 -> {DB_PATH}")
    try:
        import export
        export.export()
    except Exception as e:
        print(f"! 書き出しスキップ: {e}", file=sys.stderr)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="URLパターン限定クローラー/フェッチャー")
    ap.add_argument("patterns", nargs="*", help="URL globパターン (例: https://raw.githubusercontent.com/user/repo/main/docs/*)")
    ap.add_argument("--url-file", help="URLリスト(1行1URL)。パターン一致分のみ取得")
    ap.add_argument("--repo", help="GitHubリポジトリ全体を索引化 (例: user/repo)")
    ap.add_argument("--branch", help="--repo のブランチ (省略時はデフォルトブランチ)")
    ap.add_argument("--github-search", dest="gh_search",
                    help="GitHubリポジトリをキーワード検索し、一致したリポジトリのREADMEを索引化")
    ap.add_argument("--max-pages", type=int, default=100)
    args = ap.parse_args()
    if not args.patterns and not args.repo and not args.url_file and not args.gh_search:
        ap.error("patterns / --repo / --url-file / --github-search のいずれかを指定してください")
    crawl(args.patterns, args.url_file, args.max_pages, args.repo, args.branch,
          args.gh_search)
