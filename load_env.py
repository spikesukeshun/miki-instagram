"""
~/.zshrc から環境変数を読み込むユーティリティ。
.env が空の環境（ローカル実行）で使用する。
"""
import os
import re


def load_from_zshrc():
    """~/.zshrc の export KEY='value' / KEY='value' を os.environ にロード"""
    zshrc_path = os.path.expanduser("~/.zshrc")
    if not os.path.exists(zshrc_path):
        return
    with open(zshrc_path) as f:
        content = f.read()

    for pattern in [r"(?:export\s+)?(\w+)='([^']+)'", r'(?:export\s+)?(\w+)="([^"]+)"']:
        for m in re.finditer(pattern, content):
            key, val = m.group(1), m.group(2)
            if not os.environ.get(key):
                os.environ[key] = val
