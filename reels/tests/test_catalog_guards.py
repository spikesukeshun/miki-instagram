"""台帳（スプレッドシート）を壊さないための安全装置のテスト（Sheets には接続しない）。

  /usr/bin/python3 -m unittest reels.tests.test_catalog_guards
"""

from __future__ import annotations

import unittest

from reels.catalog import COLUMNS, HEADERS, ensure_tab


class FakeWorksheet:
    def __init__(self, title, header_row, sheet_id=2):
        self.title, self._header_row, self.id = title, header_row, sheet_id
        self.updated = []

    def row_values(self, _row):
        return list(self._header_row)

    def update(self, cell, values):
        self.updated.append((cell, values))


class FakeSpreadsheet:
    def __init__(self, worksheet):
        self._ws = worksheet
        self.sheet1 = FakeWorksheet("投稿管理", ["投稿日時"], sheet_id=1)
        self.batch_updates = []

    def worksheet(self, _title):
        return self._ws

    def batch_update(self, body):
        self.batch_updates.append(body)


class CatalogGuardTest(unittest.TestCase):
    def test_reordered_columns_stop_before_writing(self):
        # 人が列を並べ替えたまま書き戻すと、記入済みの同意・使用可否を別の値で潰す
        swapped = list(HEADERS)
        swapped[0], swapped[1] = swapped[1], swapped[0]
        ws = FakeWorksheet("リール素材台帳", swapped)
        with self.assertRaises(RuntimeError) as e:
            ensure_tab(FakeSpreadsheet(ws), "リール素材台帳", HEADERS, COLUMNS)
        self.assertIn("並び", str(e.exception))
        self.assertEqual(ws.updated, [])

    def test_missing_column_stops_too(self):
        ws = FakeWorksheet("リール素材台帳", HEADERS[:-1])
        with self.assertRaises(RuntimeError):
            ensure_tab(FakeSpreadsheet(ws), "リール素材台帳", HEADERS, COLUMNS)

    def test_empty_tab_gets_headers(self):
        ws = FakeWorksheet("リール素材台帳", [])
        ensure_tab(FakeSpreadsheet(ws), "リール素材台帳", HEADERS, COLUMNS)
        self.assertEqual(ws.updated[0][1], [HEADERS])

    def test_posting_sheet_is_never_used_as_catalog(self):
        ws = FakeWorksheet("リール素材台帳", HEADERS, sheet_id=1)
        spreadsheet = FakeSpreadsheet(ws)
        spreadsheet.sheet1 = ws
        with self.assertRaises(RuntimeError) as e:
            ensure_tab(spreadsheet, "リール素材台帳", HEADERS, COLUMNS)
        self.assertIn("投稿管理の1枚目", str(e.exception))


if __name__ == "__main__":
    unittest.main()
