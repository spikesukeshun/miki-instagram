"""Threads 実験の記録（同じスプレッドシートの別タブ）。2026-10 追加。

Instagram 用の1枚目のシート（A〜H 固定）には一切書かない。
Threads の記録は列が多く、手入力欄（空き情報・問い合わせ件数）もあるため、
別タブ `threads_posts`（投稿1件=1行）と `threads_daily`（アカウント日次=1行）に置く。

列は見出し名で読み書きする（列の並べ替えや追加で壊れないように）。
見出しは HEADERS の順でタブ作成時に書く。
"""

from __future__ import annotations

import json
import os

import gspread
from google.oauth2.service_account import Credentials

from sheet_client import SCOPES, _with_retry

POSTS_TAB = "threads_posts"
DAILY_TAB = "threads_daily"

# ステータス
ST_REVIEW = "確認待ち"      # 生成直後。人が確認して「承認済み」に変える
ST_APPROVED = "承認済み"    # 投稿対象
ST_POSTED = "投稿済み"
ST_SKIPPED = "見送り"       # 使わないことにした行（元IG投稿は再利用可に戻る）
ST_ERROR_PREFIX = "エラー："   # API失敗。同じ日の次の起動で再試行する
ST_HOLD_PREFIX = "要確認："    # 投稿前チェックで止めた。人が直して「承認済み」に戻すまで出さない

POSTS_HEADERS = [
    "予定日時",           # YYYY/MM/DD HH:MM（JST）
    "時間枠",             # 朝 / 昼 / 夜
    "ステータス",
    "型",
    "属性",               # 地域,悩み,問いかけ,CTA,空き,価格 のカンマ区切り
    "topic_tag",
    "本文",               # 投稿される本文。人が直してよい
    "本文_生成時",        # Claude が生成した原文。修正率の計算に使うので触らない
    "メディア指定",       # text / image / video / thumbnail / carousel:0,1,2
    "元IG投稿ID",
    "元IG投稿日",
    "元IG_URL",
    "生成日時",
    "投稿日時_実際",
    "Threads投稿ID",
    "Threads_URL",
    "投稿メディア_実際",  # 実際に付いたメディア（取得失敗でテキストに落ちた場合もここに残る）
    "エラー内容",
    "修正あり",           # 投稿時に 本文 と 本文_生成時 を比べて Y / N
    "空き情報",           # 手入力。空きに触れる本文はここが空だと投稿しない
    "問い合わせ件数",     # 手入力。「Threadsを見て」の問い合わせ・予約
    "指標_24h",           # JSON
    "指標_7d",            # JSON
    "指標_最新",          # JSON
    "指標_取得日時",
]

DAILY_HEADERS = [
    "日付",               # YYYY-MM-DD（JST）
    "followers_count",
    "profile_views",      # user insights の views（プロフィール閲覧数）
    "likes", "replies", "reposts", "quotes",
    "clicks",             # JSON {link_url: 回数}
    "取得日時",
    "作業時間_分",        # 手入力（週次生成・確認・返信にかかった時間）
    "メモ",
]


def _col_letter(n: int) -> str:
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


class Tab:
    """見出し行つきのワークシートを、見出し名で読み書きする薄いラッパー。"""

    def __init__(self, ws, headers: list):
        self.ws = ws
        self.headers = headers
        current = _with_retry("見出し読み取り", lambda: ws.row_values(1), 3, 5)
        if not current:
            _with_retry("見出し書き込み",
                        lambda: ws.update(range_name=f"A1:{_col_letter(len(headers))}1",
                                          values=[headers]), 3, 5)
            current = headers
        missing = [h for h in headers if h not in current]
        if missing:
            raise RuntimeError(f"タブ {ws.title} に見出しが足りません: {missing}")
        self.col = {h: current.index(h) + 1 for h in current}

    def rows(self) -> list:
        """全データ行を [(行番号, {見出し: 値})] で返す。"""
        values = _with_retry("タブ読み取り", self.ws.get_all_values, 3, 5)
        if not values:
            return []
        head = values[0]
        out = []
        for i, row in enumerate(values[1:], start=2):
            rec = {h: (row[j] if j < len(row) else "") for j, h in enumerate(head) if h}
            if any(v.strip() for v in rec.values()):
                out.append((i, rec))
        return out

    def update(self, row: int, fields: dict):
        cells = [gspread.Cell(row, self.col[k], v) for k, v in fields.items()]
        _with_retry(f"タブ更新（行{row}）", lambda: self.ws.update_cells(cells), 3, 5)

    def append(self, records: list):
        if not records:
            return
        width = max(self.col.values())
        rows = []
        for rec in records:
            row = [""] * width
            for k, v in rec.items():
                row[self.col[k] - 1] = v
            rows.append(row)
        _with_retry("タブ追記",
                    lambda: self.ws.append_rows(rows, value_input_option="RAW"), 3, 5)


def _open_spreadsheet(spreadsheet_id: str = None):
    spreadsheet_id = spreadsheet_id or os.getenv("SPREADSHEET_ID")
    if not spreadsheet_id:
        raise RuntimeError("SPREADSHEET_ID が未設定です")
    creds = Credentials.from_service_account_file("credentials.json", scopes=SCOPES)
    client = gspread.authorize(creds)
    return _with_retry("スプレッドシート取得", lambda: client.open_by_key(spreadsheet_id), 3, 5)


def _open_tab(title: str, headers: list, create: bool) -> Tab:
    book = _open_spreadsheet()
    try:
        ws = book.worksheet(title)
    except gspread.exceptions.WorksheetNotFound:
        if not create:
            raise RuntimeError(
                f"タブ {title} がありません。先に threads_plan.py register で作成してください")
        ws = _with_retry("タブ作成",
                         lambda: book.add_worksheet(title=title, rows=200, cols=len(headers)),
                         3, 5)
    return Tab(ws, headers)


def open_posts(create: bool = False) -> Tab:
    return _open_tab(POSTS_TAB, POSTS_HEADERS, create)


def open_daily(create: bool = False) -> Tab:
    return _open_tab(DAILY_TAB, DAILY_HEADERS, create)


def dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def loads(s: str):
    try:
        return json.loads(s) if s else {}
    except ValueError:
        return {}
