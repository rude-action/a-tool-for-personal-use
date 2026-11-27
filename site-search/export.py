"""index.db の索引内容をメモ帳でそのまま読めるテキストに書き出す。

- index_list.txt  : 全ページの本文込みテキスト (UTF-8 BOM付き → メモ帳で文字化けしない)
- index_list.csv  : URL/タイトル/本文の長さ/取得日時の一覧 (Excelにも対応)
- index_list.html : 一覧のHTML

usage: python export.py
"""

import csv
import html
import sqlite3

DB_PATH = "index.db"


def export():
    conn = sqlite3.connect(DB_PATH)
    try:
        rows = conn.execute(
            "SELECT url, title, content, fetched_at FROM pages ORDER BY url"
        ).fetchall()
    finally:
        conn.close()

    # メモ帳用テキスト (BOM付きUTF-8)
    with open("index_list.txt", "w", encoding="utf-8-sig", newline="\r\n") as f:
        for url, title, content, fetched in rows:
            f.write(f"{'=' * 70}\nURL: {url}\nタイトル: {title or '(無題)'}\n"
                    f"取得日時: {fetched}\n本文の長さ: {len(content)}\n{'-' * 70}\n"
                    f"{content}\n\n")

    # CSV一覧 (BOM付きUTF-8 → Excelでも文字化けしない)
    with open("index_list.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["URL", "タイトル", "本文の長さ", "取得日時"])
        for url, title, content, fetched in rows:
            w.writerow([url, title or "", len(content), fetched])

    # HTML一覧
    with open("index_list.html", "w", encoding="utf-8") as f:
        f.write('<!doctype html><meta charset="utf-8"><title>索引一覧</title>\n'
                '<style>body{font-family:sans-serif;margin:2em}'
                'td{padding:6px 12px;border-bottom:1px #ddd solid}</style>\n'
                f'<h1>索引済みページ ({len(rows)} 件)</h1><table>\n')
        for url, title, _content, fetched in rows:
            t = html.escape(title or "(無題)")
            f.write(f'<tr><td><a href="{html.escape(url)}">{html.escape(url)}</a></td>'
                    f'<td>{t}</td><td>{fetched}</td></tr>\n')
        f.write("</table>\n")

    print(f"書き出し完了: {len(rows)} 件 -> index_list.txt / index_list.csv / index_list.html")


if __name__ == "__main__":
    export()
