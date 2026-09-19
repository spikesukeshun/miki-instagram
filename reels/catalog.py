"""素材台帳（フェーズ0）とBA登録の読み書き。

台帳は Google スプレッドシートのタブ。人が見て直す欄（同意・使用可否・タグ）と、
解析で自動的に埋める欄を分けてある。再取り込みしても人が書いた欄は消さない。

使い方:
  python3 -m reels.catalog list                     # 台帳の中身を一覧
  python3 -m reels.catalog show V-xxxxxx            # 1件の詳細
  python3 -m reels.catalog tag V-xxxxxx --subjects 背中,手元 --actions 施術 \
      --framing 寄り --place 施術室 --people お客様 --face なし --note "..."
  python3 -m reels.catalog set V-xxxxxx --consent 書面 --usable 使用可
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from datetime import datetime

from reels import config

# ---------------------------------------------------------------------
# 台帳の列（この順番でシートに並ぶ）。値の選択肢は人が迷わないよう固定する
# ---------------------------------------------------------------------

KIND_VIDEO = "動画"
KIND_PHOTO = "写真"

CONSENT_CHOICES = ["未確認", "不要", "口頭", "書面"]
USABLE_CHOICES = ["未確認", "使用可", "使用不可"]
# 「施術者の手元」は手だけが写っていて誰の手か映像から確定できない場合に使う
PEOPLE_CHOICES = ["なし", "施術者の手元", "MIKI", "お客様", "お客様・施術者", "MIKI・お客様", "スタッフ"]
FACE_CHOICES = ["なし", "横顔", "正面"]
TAGGED_BY_CHOICES = ["未記入", "AI下書き", "人が確認済み"]

# 同意の強さ（要件を満たすかの比較に使う）
CONSENT_RANK = {"未確認": 0, "不要": 0, "口頭": 1, "書面": 2}


@dataclass(frozen=True)
class Column:
    key: str
    header: str
    auto: bool  # True=解析で上書きする列 / False=人（とAIの下書き）が書く列
    choices: tuple = ()


COLUMNS = [
    Column("asset_id", "素材ID", True),
    Column("kind", "種類", True),
    Column("file_name", "ファイル名", True),
    Column("drive_file_id", "DriveファイルID", True),
    Column("source_folder", "取り込み元フォルダ", True),
    Column("uploaded_at", "アップロード日", True),
    Column("analyzed_at", "解析日", True),
    Column("duration", "長さ(秒)", True),
    Column("size", "縦横(表示上)", True),
    Column("orientation", "向き", True),
    Column("rotation", "回転(度)", True),
    Column("fps", "fps", True),
    Column("hdr", "HDR", True),
    Column("audio", "音声", True),
    Column("motion", "動きの量", True),
    Column("segments", "使える区間", True),
    Column("representative", "代表フレーム(秒)", True),
    Column("contact_sheet", "一覧画像(このMac内)", True),
    Column("subjects", "被写体", False),
    Column("actions", "動作", False),
    Column("framing", "構図", False),
    Column("place", "場所", False),
    Column("people", "人物", False, tuple(PEOPLE_CHOICES)),
    Column("face", "顔の写り", False, tuple(FACE_CHOICES)),
    Column("consent", "同意", False, tuple(CONSENT_CHOICES)),
    Column("usable", "使用可否", False, tuple(USABLE_CHOICES)),
    Column("usage_history", "使用履歴", False),
    Column("tagged_by", "タグ記入", False, tuple(TAGGED_BY_CHOICES)),
    Column("note", "注意点・メモ", False),
]
COLUMN_BY_KEY = {c.key: c for c in COLUMNS}
HEADERS = [c.header for c in COLUMNS]
HUMAN_DEFAULTS = {
    "people": "",
    "face": "",
    "consent": "未確認",
    "usable": "未確認",
    "tagged_by": "未記入",
}

BA_COLUMNS = [
    Column("case_id", "BA_ID", False),
    Column("customer", "お客様（仮ID）", False),
    Column("body_part", "部位", False),
    Column("before_asset", "Before素材ID", False),
    Column("after_asset", "After素材ID", False),
    Column("before_date", "Before日付", False),
    Column("after_date", "After日付", False),
    Column("sessions", "回数（不明なら不明）", False),
    Column("treatment", "実際の施術内容", False),
    Column("allowed_text", "使ってよい説明文（この文面以外は使わない）", False),
    Column("written_consent", "書面同意", False, ("未確認", "あり", "なし")),
    Column("verified_by", "確認者", False),
    Column("verified_at", "確認日", False),
    Column("status", "状態", False, ("未確認", "確認済み")),
    Column("note", "メモ", False),
]
BA_HEADERS = [c.header for c in BA_COLUMNS]


def split_tags(value: str) -> list:
    """「背中、手元,寄り」のような書き方をタグの配列にする。"""
    if not value:
        return []
    for sep in ("、", "・", "/", "／"):
        value = value.replace(sep, ",")
    return [v.strip() for v in value.split(",") if v.strip()]


def asset_id_for(drive_file_id: str, kind: str) -> str:
    """Drive のファイルIDから、短く安定した素材IDを作る（再取り込みしても変わらない）。"""
    digest = hashlib.sha1(drive_file_id.encode("utf-8")).hexdigest()[:6]
    return ("V-" if kind == KIND_VIDEO else "P-") + digest


# ---------------------------------------------------------------------
# スプレッドシート
# ---------------------------------------------------------------------

def _open_spreadsheet():
    import gspread
    from google.oauth2.service_account import Credentials

    from sheet_client import _with_retry  # 一時的な障害のリトライは既存の実装を使う

    def _open():
        creds = Credentials.from_service_account_file(
            str(config.credentials_path()), scopes=config.GOOGLE_SCOPES)
        return gspread.authorize(creds).open_by_key(config.catalog_spreadsheet_id())

    return _with_retry("台帳スプレッドシートの取得", _open, 3, 5)


def _guard_not_posting_sheet(spreadsheet, worksheet) -> None:
    """投稿管理の1枚目（A〜H列固定）を台帳として書き換えないための安全装置。"""
    if worksheet.id == spreadsheet.sheet1.id:
        raise RuntimeError(
            f"「{worksheet.title}」は投稿管理の1枚目のシートです。台帳には使えません")


def ensure_tab(spreadsheet, title: str, headers: list, columns: list):
    """タブが無ければ作り、見出し行と選択肢（プルダウン）を設定する。"""
    import gspread

    try:
        ws = spreadsheet.worksheet(title)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=title, rows=500, cols=len(headers))
    _guard_not_posting_sheet(spreadsheet, ws)

    current = ws.row_values(1)
    if current != headers:
        if current and any(current):
            # 読み出しは見出し名で引くが、書き戻しは COLUMNS の順で流し込む。
            # 並びが違うまま書くと、人が記入した同意・使用可否の欄を別の値で潰す
            missing = [h for h in headers if h not in current]
            detail = f"足りない列: {missing}" if missing else "列の並びが違います"
            raise RuntimeError(
                f"「{title}」の見出しが想定と違います（{detail}）。"
                "このまま書き込むと人が記入した欄を上書きするため止めました。"
                "列の並びを元に戻してください")
        ws.update("A1", [headers])

    requests = [{
        "repeatCell": {
            "range": {"sheetId": ws.id, "startRowIndex": 0, "endRowIndex": 1},
            "cell": {"userEnteredFormat": {"textFormat": {"bold": True},
                                           "backgroundColor": {"red": 0.93, "green": 0.9, "blue": 0.86}}},
            "fields": "userEnteredFormat(textFormat,backgroundColor)",
        }
    }, {
        "updateSheetProperties": {
            "properties": {"sheetId": ws.id, "gridProperties": {"frozenRowCount": 1}},
            "fields": "gridProperties.frozenRowCount",
        }
    }]
    for idx, col in enumerate(columns):
        if not col.choices:
            continue
        requests.append({
            "setDataValidation": {
                "range": {"sheetId": ws.id, "startRowIndex": 1, "endRowIndex": 1000,
                          "startColumnIndex": idx, "endColumnIndex": idx + 1},
                "rule": {
                    "condition": {"type": "ONE_OF_LIST",
                                  "values": [{"userEnteredValue": v} for v in col.choices]},
                    "showCustomUi": True,
                    "strict": False,
                },
            }
        })
    spreadsheet.batch_update({"requests": requests})
    return ws


class Catalog:
    """台帳タブの読み書き。1行＝1素材。素材IDで探して上書きする。"""

    def __init__(self, spreadsheet=None):
        self.spreadsheet = spreadsheet or _open_spreadsheet()
        self.ws = ensure_tab(self.spreadsheet, config.CATALOG_TAB, HEADERS, COLUMNS)

    def _rows(self) -> list:
        from sheet_client import get_all_values_with_retry
        values = get_all_values_with_retry(self.ws)
        header = values[0] if values else HEADERS
        index = {h: i for i, h in enumerate(header)}
        rows = []
        for n, raw in enumerate(values[1:], start=2):
            if not any(raw):
                continue
            row = {c.key: (raw[index[c.header]] if index.get(c.header, 999) < len(raw) else "")
                   for c in COLUMNS}
            row["_row"] = n
            rows.append(row)
        return rows

    def all(self) -> list:
        return self._rows()

    def get(self, asset_id: str) -> dict | None:
        return next((r for r in self._rows() if r["asset_id"] == asset_id), None)

    def find_by_drive_id(self, drive_file_id: str) -> dict | None:
        return next((r for r in self._rows() if r["drive_file_id"] == drive_file_id), None)

    def upsert(self, record: dict, *, overwrite_human: bool = False) -> dict:
        """解析結果を書き込む。既存行の「人が書く列」は overwrite_human=True の時だけ上書きする。"""
        existing = self.get(record["asset_id"])
        merged = {c.key: "" for c in COLUMNS}
        merged.update(HUMAN_DEFAULTS)
        if existing:
            merged.update({k: v for k, v in existing.items() if k in COLUMN_BY_KEY})
        for key, value in record.items():
            col = COLUMN_BY_KEY.get(key)
            if col is None:
                continue
            if col.auto or overwrite_human or not (existing and existing.get(key)):
                merged[key] = "" if value is None else value
        row_values = [str(merged[c.key]) for c in COLUMNS]
        last_col = _col_letter(len(COLUMNS))
        if existing:
            self.ws.update(f"A{existing['_row']}:{last_col}{existing['_row']}", [row_values])
        else:
            rows = self._rows()
            next_row = max([r["_row"] for r in rows], default=1) + 1
            self.ws.update(f"A{next_row}:{last_col}{next_row}", [row_values])
        return merged

    def update_fields(self, asset_id: str, fields: dict) -> dict:
        row = self.get(asset_id)
        if row is None:
            raise KeyError(f"素材ID {asset_id} は台帳にありません")
        for key, value in fields.items():
            col = COLUMN_BY_KEY.get(key)
            if col is None:
                raise KeyError(f"台帳に {key} という列はありません")
            if col.choices and value not in col.choices:
                raise ValueError(f"{col.header} は {list(col.choices)} のどれかにしてください（指定: {value}）")
        return self.upsert({**{k: row[k] for k in COLUMN_BY_KEY}, **fields}, overwrite_human=True)


class BARegistry:
    """BA登録タブ。ここで「確認済み」になった組み合わせ以外は設計図で使わせない。"""

    def __init__(self, spreadsheet=None):
        self.spreadsheet = spreadsheet or _open_spreadsheet()
        self.ws = ensure_tab(self.spreadsheet, config.BA_TAB, BA_HEADERS, BA_COLUMNS)

    def all(self) -> list:
        from sheet_client import get_all_values_with_retry
        values = get_all_values_with_retry(self.ws)
        header = values[0] if values else BA_HEADERS
        index = {h: i for i, h in enumerate(header)}
        out = []
        for raw in values[1:]:
            if not any(raw):
                continue
            out.append({c.key: (raw[index[c.header]] if index.get(c.header, 999) < len(raw) else "")
                        for c in BA_COLUMNS})
        return out


def ba_case_problems(case: dict | None, catalog_ids: set) -> list:
    """BAを使ってよいかの判定。問題が1つでもあれば、そのBAカットは作らない。"""
    if case is None:
        return ["BA登録にありません"]
    problems = []
    if case.get("status") != "確認済み":
        problems.append("状態が「確認済み」ではありません")
    if case.get("written_consent") != "あり":
        problems.append("書面同意が「あり」ではありません")
    for key, label in (("body_part", "部位"), ("treatment", "実際の施術内容"),
                       ("allowed_text", "使ってよい説明文"), ("verified_by", "確認者"),
                       ("verified_at", "確認日"), ("before_asset", "Before素材ID"),
                       ("after_asset", "After素材ID")):
        if not str(case.get(key, "")).strip():
            problems.append(f"{label}が空です")
    for key, label in (("before_asset", "Before"), ("after_asset", "After")):
        asset = str(case.get(key, "")).strip()
        if asset and asset not in catalog_ids:
            problems.append(f"{label}素材 {asset} が台帳にありません")
    return problems


def _col_letter(n: int) -> str:
    letters = ""
    while n:
        n, rem = divmod(n - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


# ---------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------

def _print_row(row: dict) -> None:
    for c in COLUMNS:
        print(f"  {c.header}: {row.get(c.key, '')}")


def main(argv=None):
    from load_env import load_from_zshrc
    load_from_zshrc()

    parser = argparse.ArgumentParser(description="素材台帳の確認・タグ付け")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    show = sub.add_parser("show")
    show.add_argument("asset_id")

    tag = sub.add_parser("tag", help="被写体などのタグを書く（AIの下書きは --by AI下書き）")
    tag.add_argument("asset_id")
    for key in ("subjects", "actions", "framing", "place", "people", "face", "note"):
        tag.add_argument(f"--{key}")
    tag.add_argument("--by", default="AI下書き", choices=TAGGED_BY_CHOICES)

    setp = sub.add_parser("set", help="同意・使用可否など人が確認した結果を書く")
    setp.add_argument("asset_id")
    setp.add_argument("--consent", choices=CONSENT_CHOICES)
    setp.add_argument("--usable", choices=USABLE_CHOICES)
    setp.add_argument("--usage-history")
    setp.add_argument("--note")

    args = parser.parse_args(argv)
    catalog = Catalog()

    if args.cmd == "list":
        for r in catalog.all():
            print(f"{r['asset_id']}  {r['kind']}  {r['duration'] or '-':>5}秒  {r['orientation']}  "
                  f"動き:{r['motion'] or '-'}  被写体:{r['subjects'] or '未記入'}  "
                  f"同意:{r['consent']}  使用:{r['usable']}  {r['file_name']}")
        return 0
    if args.cmd == "show":
        row = catalog.get(args.asset_id)
        if not row:
            print(f"{args.asset_id} は台帳にありません", file=sys.stderr)
            return 1
        _print_row(row)
        return 0
    if args.cmd == "tag":
        fields = {k: getattr(args, k) for k in ("subjects", "actions", "framing", "place",
                                                  "people", "face", "note")
                  if getattr(args, k) is not None}
        fields["tagged_by"] = args.by
        _print_row(catalog.update_fields(args.asset_id, fields))
        return 0
    if args.cmd == "set":
        fields = {}
        if args.consent:
            fields["consent"] = args.consent
        if args.usable:
            fields["usable"] = args.usable
        if args.usage_history is not None:
            fields["usage_history"] = args.usage_history
        if args.note is not None:
            fields["note"] = args.note
        _print_row(catalog.update_fields(args.asset_id, fields))
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
