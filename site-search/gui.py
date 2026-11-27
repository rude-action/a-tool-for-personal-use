"""検索GUI (Tkinter / 標準ライブラリのみ)

- 上段: URLパターンを入力してクロール実行
- 下段: キーワード検索 → 結果一覧(タイトル/URL/スニペット)、ダブルクリックでブラウザ表示
"""

import sqlite3
import threading
import tkinter as tk
import webbrowser
from tkinter import messagebox, scrolledtext, ttk

import crawler

DB_PATH = crawler.DB_PATH


def run_search(query: str, limit: int = 50) -> list[dict]:
    conn = sqlite3.connect(DB_PATH)
    fts_query = " ".join(f'"{t}"' for t in query.split())
    try:
        rows = conn.execute(
            """
            SELECT p.url, p.title,
                   snippet(pages_fts, 1, '«', '»', '…', 30)
            FROM pages_fts f JOIN pages p ON p.url = f.url
            WHERE pages_fts MATCH ? ORDER BY rank LIMIT ?
            """,
            (fts_query, limit),
        ).fetchall()
    except sqlite3.OperationalError:
        rows = []
    finally:
        conn.close()
    return [{"url": u, "title": t, "snippet": s} for u, t, s in rows]


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Site-Scoped Search")
        self.geometry("900x650")
        self.results: list[dict] = []
        self._build_ui()

    def _build_ui(self):
        # --- クロール部 ---
        crawl_frame = ttk.LabelFrame(self, text="索引化 (URLパターンを指定して取得)")
        crawl_frame.pack(fill="x", padx=8, pady=6)

        ttk.Label(crawl_frame, text="種類:").grid(row=0, column=0, sticky="w", padx=4, pady=4)
        self.mode_var = tk.StringVar(value="GitHub検索")
        mode_box = ttk.Combobox(crawl_frame, textvariable=self.mode_var, width=12,
                                state="readonly", values=["GitHub検索", "GitHubリポジトリ", "URLパターン"])
        mode_box.grid(row=0, column=1, padx=4)
        mode_box.bind("<<ComboboxSelected>>", lambda e: self._mode_changed())
        ttk.Label(crawl_frame, text="入力:").grid(row=0, column=2, padx=4)
        self.input_var = tk.StringVar(value="bookmarklet")
        self.input_entry = ttk.Entry(crawl_frame, textvariable=self.input_var)
        self.input_entry.grid(row=0, column=3, sticky="ew", padx=4)
        ttk.Label(crawl_frame, text="最大ページ:").grid(row=0, column=4, padx=4)
        self.maxpages_var = tk.IntVar(value=25)
        ttk.Spinbox(crawl_frame, from_=1, to=10000, textvariable=self.maxpages_var, width=6).grid(
            row=0, column=5, padx=4
        )
        self.crawl_btn = ttk.Button(crawl_frame, text="索引化開始", command=self.start_crawl)
        self.crawl_btn.grid(row=0, column=6, padx=4)
        self.crawl_status = ttk.Label(crawl_frame, text="", foreground="gray")
        self.crawl_status.grid(row=1, column=0, columnspan=7, sticky="w", padx=4)
        crawl_frame.columnconfigure(3, weight=1)
        self._mode_hint = {
            "GitHub検索": "リポジトリをキーワード検索し、一致したリポジトリのREADMEを索引化 (例: bookmarklet)",
            "GitHubリポジトリ": "リポジトリ全体を索引化 (例: user/repo)",
            "URLパターン": "URL globパターン (例: https://example.com/docs/*)。※raw.githubusercontent.comの*.mdは実質1〜2件しか取れません",
        }

    def _mode_changed(self):
        defaults = {"GitHub検索": "bookmarklet", "GitHubリポジトリ": "user/repo",
                    "URLパターン": "https://example.com/docs/*"}
        self.input_var.set(defaults[self.mode_var.get()])
        self.crawl_status.config(text=self._mode_hint[self.mode_var.get()], foreground="gray")

        # --- 検索部 ---
        search_frame = ttk.Frame(self)
        search_frame.pack(fill="x", padx=8, pady=6)
        self.query_var = tk.StringVar()
        entry = ttk.Entry(search_frame, textvariable=self.query_var, font=("", 12))
        entry.pack(side="left", fill="x", expand=True, padx=(0, 4))
        entry.bind("<Return>", lambda e: self.do_search())
        ttk.Button(search_frame, text="検索", command=self.do_search).pack(side="left")

        # --- 結果一覧 ---
        self.tree = ttk.Treeview(
            self, columns=("title", "url"), show="headings", selectmode="browse"
        )
        self.tree.heading("title", text="タイトル")
        self.tree.heading("url", text="URL")
        self.tree.column("title", width=320)
        self.tree.column("url", width=520)
        self.tree.pack(fill="both", expand=True, padx=8, pady=4)
        self.tree.bind("<<TreeviewSelect>>", self.show_detail)
        self.tree.bind("<Double-1>", self.open_in_browser)

        self.detail = scrolledtext.ScrolledText(self, height=8, wrap="word", state="disabled")
        self.detail.pack(fill="x", padx=8, pady=(0, 8))

    # ---- 索引化 ----
    def start_crawl(self):
        value = self.input_var.get().strip()
        if not value:
            return
        mode = self.mode_var.get()
        max_pages = int(self.maxpages_var.get())
        self.crawl_btn.config(state="disabled")
        self.crawl_status.config(text="索引化中… (1ページ/秒)", foreground="gray")

        if mode == "GitHub検索":
            kwargs = dict(gh_search=value)
        elif mode == "GitHubリポジトリ":
            if value.count("/") != 1:
                messagebox.showerror("入力エラー", "user/repo の形式で指定してください")
                self.crawl_btn.config(state="normal")
                return
            kwargs = dict(repo=value)
        else:
            kwargs = dict(patterns=[p for p in value.split() if p])

        def worker():
            try:
                crawler.crawl(None, None, max_pages, **kwargs)
                n = self._page_count()
                self.after(0, lambda: self.crawl_status.config(
                    text=f"完了: 索引は {DB_PATH} に保存済み (現在 {n} ページ)", foreground="green"
                ))
            except Exception as e:
                msg = f"{type(e).__name__}: {e}"
                self.after(0, lambda: messagebox.showerror("索引化エラー", msg))
            finally:
                self.after(0, lambda: self.crawl_btn.config(state="normal"))

        threading.Thread(target=worker, daemon=True).start()

    @staticmethod
    def _page_count() -> int:
        conn = sqlite3.connect(DB_PATH)
        try:
            return conn.execute("SELECT count(*) FROM pages").fetchone()[0]
        finally:
            conn.close()

    # ---- 検索 ----
    def do_search(self):
        query = self.query_var.get().strip()
        self.results = run_search(query) if query else []
        self.tree.delete(*self.tree.get_children())
        for i, r in enumerate(self.results):
            self.tree.insert("", "end", iid=str(i), values=(r["title"] or "(無題)", r["url"]))
        if not query:
            return
        if not self.results:
            messagebox.showinfo("検索結果", "該当なし(まずクロールで索引を作成してください)")

    def show_detail(self, _event):
        sel = self.tree.selection()
        if not sel:
            return
        r = self.results[int(sel[0])]
        self.detail.config(state="normal")
        self.detail.delete("1.0", "end")
        self.detail.insert("end", f"{r['title']}\n{r['url']}\n\n{r['snippet']}\n\n(ダブルクリックでブラウザで開く)")
        self.detail.config(state="disabled")

    def open_in_browser(self, _event):
        sel = self.tree.selection()
        if sel:
            webbrowser.open(self.results[int(sel[0])]["url"])


if __name__ == "__main__":
    App().mainloop()
