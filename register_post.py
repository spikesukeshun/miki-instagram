import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from dotenv import load_dotenv
import os
import glob

load_dotenv()

SCOPES = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

FOLDER_ID = os.getenv("DRIVE_FOLDER_ID")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
GENERATED_DIR = "generated"


def get_drive_service():
    creds = Credentials.from_service_account_file("credentials.json", scopes=SCOPES)
    return build("drive", "v3", credentials=creds)


def get_sheet():
    creds = Credentials.from_service_account_file("credentials.json", scopes=SCOPES)
    client = gspread.authorize(creds)
    return client.open_by_key(SPREADSHEET_ID).sheet1


def upload_to_drive(filepath: str) -> str:
    """ファイルをGoogleドライブにアップロードしてファイル名を返す"""
    service = get_drive_service()
    filename = os.path.basename(filepath)

    # 既存ファイルがあれば削除
    results = service.files().list(
        q=f"name='{filename}' and '{FOLDER_ID}' in parents and trashed=false",
        fields="files(id)"
    ).execute()
    for f in results.get("files", []):
        service.files().delete(fileId=f["id"]).execute()

    # アップロード
    from googleapiclient.http import MediaFileUpload
    media = MediaFileUpload(filepath, mimetype="image/jpeg")
    file_metadata = {"name": filename, "parents": [FOLDER_ID]}
    service.files().create(body=file_metadata, media_body=media, fields="id").execute()

    print(f"  アップロード完了: {filename}")
    return filename


def register(
    post_datetime: str,
    menu_type: str,
    caption: str,
    hashtags: str,
    memo: str = "",
):
    """generatedフォルダの画像ファイル名を確認してスプレッドシートに登録"""

    # generatedフォルダの画像を取得
    files = sorted(glob.glob(os.path.join(GENERATED_DIR, "carousel_*.jpg")))
    if not files:
        print("generated/ フォルダに画像が見つかりません")
        return

    filenames = [os.path.basename(f) for f in files]
    files_str = ",".join(filenames)

    print(f"\n以下の{len(filenames)}枚をGoogleドライブの「instagram投稿素材」フォルダに入れてください：")
    for name in filenames:
        print(f"  - {name}")
    print("\nFinderで /Users/shunsuke/Desktop/美喜のinstagram/generated/ を開いて")
    print("全ファイルをGoogleドライブにドラッグ＆ドロップしてください。")
    input("\n完了したらEnterを押してください...")


    # スプレッドシートに登録
    sheet = get_sheet()
    row = [post_datetime, menu_type, files_str, caption, hashtags, memo, "未投稿"]
    sheet.append_row(row)

    print(f"\nスプレッドシートに登録完了！")
    print(f"  投稿日時: {post_datetime}")
    print(f"  画像: {len(filenames)}枚")
    print(f"  ステータス: 未投稿")
    print(f"\nGOを出すにはGitHub Actions → Run workflow を押してください！")


if __name__ == "__main__":
    register(
        post_datetime="2026/04/07 21:00",
        menu_type="ブライダルエステ",
        caption="""MIKIです。

なぜブライダルエステを始めたのか、
今日は少し自分語りさせてください😊

美容学校でトータルビューティを学んだことが
私のすべての原点です。

ヘア・メイク・ネイル、そしてエステ。
女性の美しさを多角的に捉える視点を養う中で、

土台となる肌や体、メンタルを整えることが
全ての美しさの根幹である。

という確信を持ちました。

「エステが初めてで何もわからない」
「いつから始めればいいかわからない」
「ブライダルエステを検索してもたくさんありすぎてわからない」
「料金が不明確で勧誘が不安」

そんな小さな不安や迷いを
一番最初に打ち明けてもらえる存在でいたい。

私自身が一人の花嫁になった時、
現実は想像以上に大変なものでした。

溢れる情報の中で、
肌や体の悩み、そして尽きない不安に
私自身も深く迷いました。

ブライダルエステは単に外見を整えるだけの場所ではなく、
プロとして確かな技術を提供するのはもちろん、
花嫁様が抱える小さな不安や迷いに寄り添い、
一番の理解者として、支える存在でありたいと思いました。

これまで多くの花嫁様を施術させていただく中で、
お体や肌が変わっていくと自信に満ちた笑顔になっていく姿を拝見してきました。

その瞬間に立ち会えることが今の私の最大の喜びです。

結婚式が終わって、ライフステージが変わっても、
「またMIKIに会いたいな」と
ふと思い出してもらえたら嬉しいです。

美容と健康に興味がある。
素直に自分と向き合える。
ダイエットがなかなか続かない😂

そんな花嫁様、ぜひ一度会いに来てください🌸

---

✨ MIKI指名　初回限定20%OFF ✨

ご予約・ご相談はプロフィールのDMから
お気軽にどうぞ💌""",
        hashtags="#ブライダルエステ #ブライダルエステ東京 #ブライダルエステ体験 #プレ花嫁2026 #大人花嫁 #東京花嫁 #六本木エステ",
        memo="ブライダルエステを始めたきっかけ",
    )
