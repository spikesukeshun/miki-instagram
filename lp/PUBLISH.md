# LP 公開 — 引き継ぎ

作成: 2026-08-13 ／ 制作の引き継ぎは `HANDOFF.md`（このファイルは**公開作業だけ**を扱う）

---

## 0. 結論から

**LPの中身は完成していて、あとは「どこに置くか」を決めるだけ。**
ただし **Artifact 以外の場所に置くなら、先に必ずやる作業が2つある**（→ 2章）。
何も足さずにそのままサーバに置くと**レイアウトが崩れる**。

---

## 1. 現在の状態

| 項目 | 値 |
|---|---|
| ソース | `/Users/shunsuke/Desktop/美喜のinstagram/lp/index.html`（単一ファイル・**2.8MB**） |
| ブランチ | `lp/conversion-landing-page` — **origin に push 済み・未pushコミット 0** |
| 最新コミット | `e073a74` |
| 現在の公開先 | Artifact `https://claude.ai/code/artifact/0339725a-6a87-493d-b337-dd920153489f` |
| 埋め込み画像 | 29点すべて data URI（JPEG 14 / WebP 15）。**外部ファイル参照は0**。CSS・JSもインライン |

**Artifact は既定で非公開。** 他人が見られる状態にするには、ページの共有メニューから
ユーザー本人が共有操作をする必要がある（この操作はAIからは実行できない）。

---

## 2. Artifact 以外に置くなら「先に」必要な作業

### 2-1. HTMLの殻を付ける（**省略不可**）

`lp/index.html` は **`<!doctype>` / `<html>` / `<head>` / `<body>` を持っていない**。
先頭がいきなり `<title>` から始まる。これは Artifact が公開時に殻を付ける仕様に合わせたため。

**このまま普通のサーバに置くと quirks モードになり、`body{overflow-x:hidden}` が効かず
横スクロールが壊れる。** 必ず下記で包むこと。

```html
<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<!-- ここに 2-2 の meta を入れる -->
</head>
<body>
<!-- lp/index.html の中身をそのまま -->
</body>
</html>
```

検証用サーバ（`HANDOFF.md` 5章）がまさにこれをやっているので、
`scratchpad/serve.py` の `HEAD` / `TAIL` を流用すればよい。
**ただし `TAIL` の reveal 無効化スクリプトは撮影用なので本番には入れないこと**（アニメーションが死ぬ）。

### 2-2. OGP / meta を足す（**推奨・強く**）

現状 **`<meta>` タグが1つも無い**。このままだと LINE・Instagram・X に URL を貼っても
**サムネイルも説明文も出ない**（タイトルだけの寂しいリンクになる）。
Instagram のプロフィール欄から誘導する前提なら、ここは効く。

必要なもの：

- `description`
- `og:title` / `og:description` / `og:image` / `og:url` / `og:type=website`
- `twitter:card=summary_large_image`
- favicon（現在 Artifact 側で 🌿 を指定しているだけなので、自前ホストでは別途必要）

⚠ **`og:image` は data URI が使えない。** SNSのクローラは実ファイルのURLしか読まない。
1200x630 の画像を1枚だけ**別ファイルとして**書き出して置く必要がある。
素材候補：コンセプト写真（施術ルーム）＋「MIKI ／ 六本木」の文字。

---

## 3. 置き場所の選択肢

### 案A：Artifact のまま共有（いちばん早い）

- 作業ゼロ。2章の対応も不要（Artifact が殻を付けてくれる）。
- URLが `claude.ai/code/artifact/...` になる。**サロンのLPとしては見た目が良くない**。
- OGPは付けられない。
- 更新は今までどおり（`url` を渡して再publish）。

### 案B：GitHub Pages（このリポジトリで既に稼働中）

**すでに `https://spikesukeshun.github.io/miki-instagram/` が生きている**（HTTP 200 確認済み）。
設定は `main` ブランチの `/docs`（`register_post.py` の `setup_github_pages()` が有効化したもの）。

⚠ **`docs/index.html` は既に「MIKI Instagram AIダッシュボード」が使っている。**
ここを上書きするとダッシュボードが消える。**LPは `docs/lp/index.html` に置くこと**
→ `https://spikesukeshun.github.io/miki-instagram/lp/`

- 2章の対応（殻＋OGP）が必要。
- LPは `lp/conversion-landing-page` ブランチにあり、Pages は `main` から配信している。
  **どうやって main に持っていくか**を決める必要がある（マージするか、ビルド成果物だけ置くか）。
- 2.8MB の単一ファイル。GitHub Pages のソフトリミット（推奨1GB・ファイル100MB）には余裕。
  ただし**初回表示で2.8MBを一気に読む**ので、モバイル回線では体感が重い可能性がある。
  気になるなら画像を別ファイル化して遅延読み込みにする改修が要る（今は全部data URI）。

### 案C：独自ドメイン

案Bに `CNAME` を足す形が一番素直。ドメイン取得・DNS設定はユーザー作業。
サロンの信頼感は一番高い。

---

## 4. 決めてもらう必要があること

1. **どこに置くか**（案A / B / C）
2. 案B・Cなら **main への持っていき方**（`lp/conversion-landing-page` をマージするか、成果物だけ置くか）
3. **OGP画像を作るか**（作るなら素材の指定。無くても公開はできるが、SNS経由の見え方が弱い）
4. **2.8MB のままで良いか**（画像分割＋遅延読み込みをするか）

---

## 5. 公開前に片付けたい内容の課題

`HANDOFF.md` 2章から、公開に関係するものだけ再掲：

- **口コミNo.1 の根拠待ち**：現在LPは「20・30代のお客様に ご好評」に退避済みで、
  "No.1" はページ内0件。**このまま公開して問題ない。**
  根拠が届いたら「調査主体／時期／範囲」を併記した形でのみ戻すこと（景表法）。
- **カルーセル投稿側のCTA文言と不一致**：LPは「MIKI指名 20%OFF ・ VIPコース(150分/180分)限定」、
  投稿側は CLAUDE.md の恒久ルールで「MIKI指名 初回限定20%OFF（VIPコースのみ）」。
  **「初回限定」の有無が食い違っている。** 公開前にどちらが正しいか確認したほうがよい。

---

## 6. 注意（公開作業とは別だが、気づいた点）

**内部向けのAIダッシュボードが、いま誰でも見られる状態にある。**
`https://spikesukeshun.github.io/miki-instagram/` — URLを知っていれば誰でも開ける。
インサイト数値などが載っているので、意図した公開かどうか確認したほうがよい。
意図していないなら、Pagesを止めるか、ダッシュボードを別の非公開の場所へ移す必要がある。

なお `.env` / `credentials.json` / `client_secrets.json` は
`.gitignore` で除外済みであることを確認済み（リポジトリには入っていない）。

---

## 7. 引き継ぎ後、最初にやること

1. このファイルと `HANDOFF.md` の 1章・5章（検証方法）を読む
2. 上の「4. 決めてもらう必要があること」をユーザーに確認する
3. 案が決まったら、2章の殻とOGPを付けてから配信する
4. 配信後は**実機で**表示を確認する。
   ⚠ ヘッドレスChromeは375pxを再現できない（innerWidthが500に丸まる）。
   375px検証は in-app ブラウザの `resize_window(preset:"mobile")` で行うこと。
