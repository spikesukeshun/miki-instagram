# 案B 投稿スタイルの試作記録

2026-09-21〜27 に作った案B（全面写真）の試作と、その後の扱い。
**このフォルダの content は試作。シートには登録していない。**

レイアウトの仕様は `rules/carousel-design.md`、フィールドは `rules/content-schema.md` が正。
ここには「どの試作がどこにあり、どう作り直すか」だけを書く。

## 一覧

| 形式 | 状態 | プレビュー |
|---|---|---|
| flipbook（パラパラ漫画・10枚） | 試作 | https://spikesukeshun.github.io/miki-instagram/proto-flipbook/ |
| phrase（全面写真＋文節・9枚） | 試作 | https://spikesukeshun.github.io/miki-instagram/proto-phrase/ |
| mosaic A（1枚の写真を9分割・10枚） | 試作・**コード未実装** | https://spikesukeshun.github.io/miki-instagram/proto-mosaic-a/ |
| mosaic B（9枚の別写真・10枚） | **実装済み・2026/10/01 21:00 に本登録** | 本編のプレビュー（シートH列） |

`proto-*` のページは slug が日付形式でないので、投稿後の自動削除（`post_scheduler.py` /
`cleanup_posted.py`）の対象にならない。不要になったら GitHub の `docs/proto-*/` と
`generated/proto-*/` を手で消す。

**試作プレビューを日付の slug に置かないこと。** 当初は 2026-09-28-2200 / 2026-10-01-2100 に
置いていたが、シートから外して枠を空けたため、土曜の定期タスクが本編で同じ slug を上書きした。
試作画像の原本は git 履歴にある（flipbook: `0fab2ef`、phrase: `5364b67` の `generated/<slug>/`）。

## content の扱い

`content_proto-*.json` は `post_datetime` と `_generated_dir` を**わざと消してある**。
元の値は実在の投稿枠（9/28・10/1）で、そのまま `create_post.py` に通すと本編の枠を上書きするため。
作り直すときは空いている枠を確認してから `--post-datetime` を明示する
（ファイル名からも日時が取れないので、付け忘れると `PostTargetUnresolved` で止まる）。

## flipbook

- 素材: Drive「動画」`IMG_9981.MOV`（インディバ）の 44.0〜45.6 秒を 0.2 秒間隔で9コマ ＋ 案B版CTA
- コマの抜き直し（cleanup で消えるので作り直すたびに必要）:
  `/usr/bin/python3 preview_drive_videos.py --file IMG_9981.MOV --frames 9 --at 44.0 --window 1.6 --save-frames backgrounds`
- **MIKIさんに未確認の記述**: 「痛さではなく、じんわりとした温かさ」「もう片方の手で様子を確かめながら」

## phrase

- 一文: お客様が／自信に／満ちた／笑顔に／なっていく／その瞬間に／立ち会えることが／今の私の／最大の喜びです
- **差し替え保留**: 1枚目（背中にタトゥーの花嫁）と3枚目（口元が写る花嫁・拡大率が高い）
- 差し替えは `reuse_filename` を書き換えて作り直すだけ

## mosaic

- B は `post_style: "mosaic"` ＋ `tile` 型として実装済み。文字は白＋影
  （案Bでシャドウを使うのはこの型だけ。`check_repo_sync.py` が見張る）
- **A（1枚の写真を9分割）は未実装。** ユーザー指定の仕様は次のとおり:
  - 影は使わない
  - 区画ごとに文字の下の明るさを測り、明るければ墨・暗ければ白
  - 文字サイズは全区画で統一（B と同じ）
- 白一色にできない理由: Red Bull の投稿が素の白で成立するのは写真が暗いから。
  Drive のメニュー写真14枚のうち、文字が載る下部が暗いのは4枚だけだった。
  白一色では9区画中6区画で文字が飛び、墨一色では暗い区画で沈む
