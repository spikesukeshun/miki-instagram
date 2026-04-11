"""
GitHub Actions 実行前の事前チェックスクリプト
Claude Code がローカルで実行して問題がないか確認する。
"""
import json
import subprocess
import sys
import urllib.request
import urllib.error

REPO = "spikesukeshun/miki-instagram"

REQUIRED_SECRETS = {
    "check_revisions.yml": [
        "GOOGLE_CREDENTIALS",
        "SPREADSHEET_ID",
        "LINE_CHANNEL_ACCESS_TOKEN",
        "LINE_USER_ID_SHUNSUKE",
        "LINE_USER_ID_MIKI",
        "GROQ_API_KEY2",
    ],
    "post.yml": [
        "GOOGLE_CREDENTIALS",
        "SPREADSHEET_ID",
        "INSTAGRAM_ACCESS_TOKEN",
        "INSTAGRAM_BUSINESS_ACCOUNT_ID",
        "DRIVE_FOLDER_ID",
    ],
}

ok = True


def check(label, passed, detail=""):
    global ok
    status = "OK" if passed else "NG"
    msg = f"[{status}] {label}"
    if detail:
        msg += f"  ({detail})"
    print(msg)
    if not passed:
        ok = False


def get_token():
    try:
        url = subprocess.check_output(
            "git remote get-url origin", shell=True, text=True, stderr=subprocess.DEVNULL
        ).strip()
        if "ghp_" in url:
            return url.split(":")[2].split("@")[0]
    except Exception:
        pass
    return None


# ── 1. credentials.json のローカル検証 ──────────────────────────────
print("\n--- ローカル credentials.json ---")
try:
    content = open("credentials.json").read().strip()
    check("credentials.json が空でない", bool(content))
    if content:
        data = json.loads(content)
        check(
            "type = service_account",
            data.get("type") == "service_account",
            f"type={data.get('type','?')}",
        )
        check("project_id が存在する", bool(data.get("project_id")), data.get("project_id", "?"))
        check("client_email が存在する", bool(data.get("client_email")))
except FileNotFoundError:
    check("credentials.json が存在する", False, "ファイルなし")
except json.JSONDecodeError as e:
    check("credentials.json が有効なJSON", False, str(e))

# ── 2. GitHub シークレット登録確認 ──────────────────────────────────
print("\n--- GitHub シークレット登録状況 ---")
token = get_token()
if not token:
    print("[SKIP] GitHub トークンが取得できませんでした")
else:
    try:
        req = urllib.request.Request(
            f"https://api.github.com/repos/{REPO}/actions/secrets?per_page=100",
            headers={"Authorization": f"token {token}", "Accept": "application/vnd.github+json"},
        )
        with urllib.request.urlopen(req) as r:
            registered = {s["name"] for s in json.load(r)["secrets"]}

        all_required = set()
        for secrets in REQUIRED_SECRETS.values():
            all_required.update(secrets)

        for name in sorted(all_required):
            check(f"{name} が登録済み", name in registered)
    except urllib.error.HTTPError as e:
        print(f"[SKIP] GitHub API エラー: {e.code} {e.reason}")

# ── 3. ワークフロー YAML の文法確認 ─────────────────────────────────
print("\n--- ワークフロー YAML 文法 ---")
try:
    import yaml  # type: ignore

    for wf in ["check_revisions.yml", "post.yml"]:
        try:
            yaml.safe_load(open(f".github/workflows/{wf}"))
            check(f"{wf} の文法が正常", True)
        except yaml.YAMLError as e:
            check(f"{wf} の文法が正常", False, str(e)[:80])
except ImportError:
    print("[SKIP] PyYAML が未インストールのため YAML 検証をスキップ")

# ── 結果 ──────────────────────────────────────────────────────────────
print()
if ok:
    print("✓ すべてのチェックが通過しました。GitHub Actions を実行できます。")
else:
    print("✗ 問題が検出されました。上記の NG 項目を修正してください。")
    sys.exit(1)
