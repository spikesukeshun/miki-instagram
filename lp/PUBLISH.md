# LP 公開 — 引き継ぎ

作成: 2026-08-13 ／ 更新: 2026-08-14
制作の引き継ぎは `HANDOFF.md`（このファイルは**公開作業だけ**を扱う）

---

## 0. 現在の状態

### ✅ 公開済み（2026-08-14）

```
公開URL   https://www.esthe-miki.workers.dev/     ← 稼働中
アカウント s.bsb.o.s1+miki@gmail.com（サロン専用）
Account ID f1ef33518ca7a7621b0d1c3de3d1e533       ← wrangler.jsonc に固定済み
ソース    lp/index.html （唯一の正・変更しない）
ビルド    lp/tools/build_site.py → lp/dist/
配信      lp/wrangler.jsonc （Workers Static Assets）
```

**Artifact は削除せず現状のまま残している。** `lp/index.html` を変更しない設計なので、
Artifact 版は今までどおり動く（バックアップ兼プレビュー）。

### 残っている作業（美喜さんの操作が必要）

| # | 作業 | 状態 |
|---|---|---|
| 1 | Cloudflare アカウント作成 | ✅ 完了 |
| 2 | `wrangler login` | ✅ 完了 |
| 3 | **GA4 プロパティ作成** → 測定IDを `--ga4-id` でビルドに渡す | ⬜ 未 |
| 4 | **Google Search Console 登録** → トークンを `--gsc-token` で渡す | ⬜ 未 |
| 5 | **Bing Webmaster Tools 登録**（GSCからインポート） | ⬜ 未 |
| 6 | Instagram プロフィールのURLに `?utm_source=instagram` を付ける | ⬜ 未 |

⚠ **GA4を有効にすると `privacy.html` が自動生成され、フッターに告知が入る。**
Google アナリティクス利用規約が要求するため（→ 3-2章）。GA4を入れないビルドでは
ページごと出力しない（使っていない告知を置かないため）。

---

## 1. なぜ GitHub Pages をやめたか

当初は Artifact / GitHub Pages / 独自ドメイン の3案で検討していたが、
**GitHub Pages は技術面以前に規約で不適格**と判明した。

| 候補 | 商用利用 | 判定 |
|---|---|---|
| GitHub Pages | ❌ | **不可**。ToSが「オンラインビジネスの運営や、**商取引の促進を主目的とするサイト**の無料ホスティング利用」を禁止。予約獲得が目的のサロンLPは該当する |
| Vercel 無料枠 | ❌ | **不可**。Hobbyは非商用限定で「法人所有のプロジェクト」を名指しで禁止 |
| Netlify 無料枠 | ✅ | 可。商用OK（禁止はホスティング再販のみ）。月100GB転送 |
| **Cloudflare Workers 無料枠** | ✅ | **採用**。商用OK・1日10万リクエスト |
| 国内レンタルサーバ | ✅ | 可。月100〜500円。デプロイ自動化はしにくい |

Netlify と実質互角だが、**すでにアカウントと運用経験がある**こと、国内CDNが速いこと、
独自ドメインへの移行が滑らかなことから Cloudflare を採用。

**副次的な利点**：ダッシュボードと別ドメインになる。GitHub Pages に同居させると、
LPを Search Console に登録した時点で Google が同一サイト内のダッシュボードと
投稿プレビューも探しに来るが、これが構造的に起きない。

### 実測で確認したこと

- `workers.dev` は `x-robots-tag` ヘッダ無し・robots.txt に `Disallow` ゼロ
  → **インデックスを拒否していない**
- `workers.dev` は Public Suffix List の12730行目に実在
  → Search Console は**ドメインプロパティが使えない。URLプレフィックス一択**
- `_headers` は Workers Static Assets で正式サポート

---

## 2. 仕組み（なぜビルドが要るのか）

`lp/index.html` は **Artifact 用に作られている**。

- `<!doctype>` / `<html>` / `<head>` / `<body>` を持たない（Artifactが公開時に付ける）
- 画像29点をすべて data URI で自己完結（ArtifactのCSPは外部リクエストを一切許さない）

**このまま普通のサーバに置くと quirks モードになり `body{overflow-x:hidden}` が効かず
横スクロールが壊れる。** さらに 2.8MB を一気に読むことになる。

かといって `lp/index.html` に殻を書き足すと **Artifact 経由の更新経路が壊れる**。
そこで**ビルドスクリプトが両方を吸収する**構成にした。

```
                lp/index.html （唯一の正・変更しない）
                      │
      ┌───────────────┴───────────────┐
      ▼                               ▼
Artifact（現状維持）            build_site.py
自己完結・data URI                     │
CSP制約あり                            ▼
                                lp/dist/ → Cloudflare Workers
                                殻あり・画像外部化・SEO対応
```

### build_site.py がやること

| 処理 | 効果 |
|---|---|
| 殻（doctype/head/body）を被せる | quirks モードを回避 |
| data URI 29点を外部ファイル化 | **HTML 2,878KB → 151KB（94.8%削減）** |
| JPEG 14点を WebP に変換 | 画像 2,048KB → 1,538KB（511KB削減） |
| `<img>` 13点に `loading="lazy"` | 初回は読まない。全部ファーストビュー外なので安全 |
| ヒーロー/コンセプト写真を `preload` | この2点はCSS背景でlazyにできないので逆に優先させる |
| SEO用 head（meta/OGP/JSON-LD） | 下記3章 |
| `ogp.jpg` 1200x630 を生成 | SNSのサムネイル |
| `robots.txt` / `sitemap.xml` / `_headers` / `404.html` | 下記3章 |

⚠ **data URI は文字列そのものを全文置換する。** `<img src>` 13点だけでなく
CSS `background-image` 14点と**カスタムプロパティ 2点**（`--hero-img` / `--concept-img`）にも
入っているため、文脈で見分ける方式は取りこぼす。

⚠ **`HANDOFF.md` 5章 serve.py の `TAIL`（reveal 無効化）は撮影用。本番ビルドに入れないこと**
（アニメーションが死ぬ）。

---

## 3. SEO で入れたもの

### 狙い

**「MIKI 六本木 エステ」のような指名検索**と、**AI検索（ChatGPT / Copilot）**。

「六本木 エステ」のような一般検索はホットペッパー等が独占していて、
1ページのLPでは勝てない。**ここは狙わない。**

### 入れたもの

- `title`（Web版だけ上書き。Artifact版の `<title>` はそのまま）
- `description` / `canonical` / OGP一式 / `twitter:card` / favicon
- **JSON-LD**：`Person`（MIKI）+ `ProfessionalService` + `WebSite`
- `robots.txt`：検索・AI回答・AI学習すべて許可（`Content-Signal: search=yes, ai-input=yes, ai-train=yes`）
- `sitemap.xml`
- `_headers`：`/img/*` は1年 immutable（内容ハッシュ名なので安全）、HTMLは5分
- `404.html`：**ソフト404にしない**（トップへリダイレクトするとインデックス品質が落ちる）

⚠ **`LocalBusiness` とサロン名・住所は入れていない。** CLAUDE.md の絶対ルール
「サロン名を書かない」に抵触するため。指名検索を取る目的には Person で足りる。
本文のアクセスセクションにだけサロン名があるが、これは `HANDOFF.md` 303行の
**ユーザー判断による承認済みの例外**。

## 3-2. アクセス解析（GA4）とプライバシーポリシー

`site.json` の `ga4_measurement_id` に `G-` で始まる測定IDを入れると、
GA4 の計測タグ・**予約導線のクリック計測**・`privacy.html`・フッター告知が
まとめて有効になる。空なら何も出力しない。

計測するイベント：

| イベント | 内容 |
|---|---|
| `cta_dm` | DMボタンのクリック。**そのとき選択中だったコース名**も送る |
| `cta_hotpepper` | ホットペッパーのクリック。コース名＋クーポンID |

⚠ 既存の予約導線ロジック（`data-hp-target` のURL差し替え）には触っていない。
キャプチャ段階の受動的なリスナーで観測するだけ。動作確認済み。

### GA4 プロパティ作成時の選択（2026-08-14 決定）

⚠ **ビジネス目標は作成後に変更できない**（Googleヘルプ：「ビジネス情報を変更しても
ビジネス目標別コレクションはカスタマイズされません」）。ただし選択が変えるのは
**表示されるレポートの組み合わせだけ**で、収集されるデータは変わらない。
後から必要になれば「探索」で自作できる。

| 項目 | 選択 | 理由 |
|---|---|---|
| ビジネス目標「見込み顧客の発掘」 | ✅ 選ぶ | ユーザー獲得／トラフィック獲得／ランディングページ。流入把握の中核 |
| ビジネス目標「ユーザー行動の調査」 | ✅ 選ぶ | **イベントレポート**。`cta_dm` / `cta_hotpepper` がここに出る。**外さないこと** |
| ビジネス目標「オンライン販売の促進」 | ❌ | 予約はホットペッパー側で完結し購入イベントを送っていないので空になる |
| ビジネス目標「ブランド認知度の向上」 | ❌ | 広告を出さないので空。ユーザー属性もしきい値で伏せられる規模 |
| データ共有「Google のプロダクトとサービス」 | ❌ OFF | 共有範囲が最も広い。Google広告を始めるならONに戻す |
| データ共有「モデリングのためのデータ提供とビジネス分析情報」 | ✅ ON | 業界ベンチマークが見られる |
| データ共有「テクニカル サポート」 | ✅ ON | 不具合時にGoogleが設定を見られる |
| データ共有「アカウント スペシャリスト」 | ❌ OFF | 実質的に営業連絡の受け入れ |
| **データ処理規約（GDPR）** | ✅ 同意 | 下記参照 |
| データ保持期間 | 14か月に変更 | 初期値2か月では前年同月比が見られない |

### 法令・規約の整理（調査済み）

**GDPR のデータ処理規約には同意する。**
このLPは日本語のみ・円建て・国内向け予約導線なので、GDPRの域外適用（EU居住者への
サービス提供／域内での行動監視）には通常あたらない。**が、同意に代償がない**
（Googleが処理者としての義務を負う契約条項で、機能・料金・データ収集は変わらない）。
六本木は外国人客が多く、将来英語ページを作れば判断が変わりうるため、
「たぶん要らないがタダで持てる保険」として受けておく。
併記される「測定データ管理者間のデータ保護に関する条項」も同様。


- **改正電気通信事業法の「外部送信規律」は、このLPには適用されない。**
  対象は「他人の需要に応ずるため」に電気通信役務を提供する事業者。総務省ガイドラインでは
  **企業・個人が自己の情報発信のために運営するサイトは「自己の需要のため」で対象外**とされる。
  サロンが自分のサービスを紹介して予約を受けるLPはこれに当たる
- **ただし Google アナリティクス利用規約 第7条がプライバシーポリシーの掲示を義務付けている。**
  これは法令ではなく Google との契約上の義務。要求は4点で、`privacy.html` がすべて満たしている：
  ① ポリシーの掲示 ② Cookie・端末識別子の使用告知 ③ GAの使用と収集・処理方法の開示
  ④ 「Googleのサービスを使用するサイトからの情報のGoogleによる使用」への目立つリンク

⚠ 法的助言ではない。最終的な妥当性が問われる場面では専門家に確認すること。

### 検索エンジンごとの扱い

| エンジン | 対応 |
|---|---|
| Google | Search Console に登録（→ 4章C） |
| **Yahoo! JAPAN** | **追加作業ゼロ。** 2010年12月からGoogleのエンジンを使用。契約は**2027年3月31日まで**。Google対策＝Yahoo対策 |
| Bing | 別途登録する価値あり。**ChatGPTの検索がBingインデックスに依存**しているため（→ 4章D） |

---

## 4. 残っている作業（美喜さんの操作が必要）

私が代行できないのは**アカウント作成・パスワード入力・OAuth承認**だけ。それ以外は実装済み。

### A. Cloudflare アカウントの新規作成

1. https://dash.cloudflare.com/sign-up
2. **既存の tkp アカウントとは別のメールアドレス**で登録
   （`s.bsb.o.s1+miki@gmail.com` のようなエイリアスでも別アカウントとして通る）
3. 確認メールのリンクでメール認証
4. 左メニューの **「Compute (Workers)」**（または「Workers & Pages」）を開く
5. 初回に**サブドメインを決める画面**が出る → **`esthe-miki`** と入力して確定
   - ⚠ **ここが公開URLの一部になる。** 後から変えるとURLごと変わる
   - 空きは調査済み（`*.esthe-miki.workers.dev` は名前解決しない＝未登録）

### B. wrangler へのログイン

```bash
source ~/.nvm/nvm.sh && nvm use 24 && npx wrangler login
```

⚠ **ブラウザが tkp アカウントでログイン中だとそちらに紐づく。**
開いた画面が新アカウントか確認してから「Allow」。

### C. Google Search Console

**これをやらないと Google はページの存在に気づかない。** LPへのリンクは現状ゼロで、
Instagram プロフィール欄のリンクは `l.instagram.com` 経由の nofollow のため当てにできない。

1. https://search.google.com/search-console
2. 「プロパティを追加」
3. ⚠ **左の「ドメイン」ではなく右の「URLプレフィックス」**（workers.dev は Public Suffix List にあるため）
4. `https://www.esthe-miki.workers.dev/` を入力
5. 確認方法「**HTMLタグ**」→ `content="..."` の値を控える
6. ビルドに埋める：

   ```bash
   /usr/bin/python3 lp/tools/build_site.py --gsc-token <控えた値>
   ```

   （`lp/site.json` に保存されるので次回以降は指定不要）
7. デプロイ後、Search Console で「確認」を押す
8. 「サイトマップ」→ `sitemap.xml` を送信
9. 「URL検査」→ トップURL → 「インデックス登録をリクエスト」

⚠ 実際に載るまで**数日〜数週間**かかる。すぐ出なくても異常ではない。

### D. Bing Webmaster Tools（Cの後が楽）

1. https://www.bing.com/webmasters
2. 「**Google Search Console からインポート**」を選ぶ
3. Googleアカウントで承認 → サイトを選んでインポート
4. IndexNow キーを取得したら `--indexnow-key <値>` でビルドすればキーファイルが配置される

⚠ Cloudflare の IndexNow 自動連携（Crawler Hints）は**ゾーン単位の機能で
workers.dev では使えない見込み**。独自ドメイン移行後は切り替えられる。

---

## 5. 日常の運用（重要）

**LPを更新するときは2か所を更新する。片方だけだと Artifact と Web版が乖離する。**

```bash
# 1. lp/index.html を編集（ここが唯一の正）

# 2. Artifact を更新 — ⚠ url パラメータを必ず渡す（HANDOFF.md 1章）
#    Artifact(file_path: ".../lp/index.html",
#             url: "https://claude.ai/code/artifact/0339725a-6a87-493d-b337-dd920153489f",
#             favicon: "🌿", description: "...")

# 3. Web版をビルドしてデプロイ
/usr/bin/python3 lp/tools/build_site.py
source ~/.nvm/nvm.sh && nvm use 24 && npx wrangler deploy --config lp/wrangler.jsonc
```

⚠ **wrangler は Node 22+ が必要。** 既定は v20.14.0 なので `nvm use 24` を必ず挟む。

---

## 6. デプロイ後に必ず確認すること

```bash
# 配信とヘッダ
curl -sS -D - -o /dev/null https://www.esthe-miki.workers.dev/

# ★未検証: 自前の robots.txt が Cloudflare の既定を上書きできているか
curl -sS https://www.esthe-miki.workers.dev/robots.txt

# sitemap と OGP画像（og:image が404だとサムネイルが出ない）
curl -sS -o /dev/null -w "%{http_code}\n" https://www.esthe-miki.workers.dev/sitemap.xml
curl -sS -o /dev/null -w "%{http_code} %{content_type}\n" https://www.esthe-miki.workers.dev/ogp.jpg

# 404 が 404 ステータスで返るか（ソフト404になっていないか）
curl -sS -o /dev/null -w "%{http_code}\n" https://www.esthe-miki.workers.dev/no-such-page

# 画像の長期キャッシュ
curl -sS -D - -o /dev/null https://www.esthe-miki.workers.dev/img/<hash>.webp | grep -i cache-control
```

さらに **375px の実機確認**。
⚠ **ヘッドレスChromeは375pxを再現できない**（innerWidth が500に丸まる／`HANDOFF.md` 5章）。
in-app ブラウザの `resize_window(preset:"mobile")` を使うこと。

---

## 7. ローカル検証で確認済みのこと（2026-08-14）

ビルド版とビルド前を同一条件で撮影して比較した結果：

| 項目 | 結果 |
|---|---|
| 画素一致（差≦12） | **99.86%** — 残差はWebP再圧縮による微差 |
| 表示崩れ（差>60の行） | **ゼロ** |
| 375px 横溢れ | **なし**（`scrollWidth === innerWidth === 375`） |
| 375px ページ高 | ビルド前と**完全一致**（18550px） |
| ホットペッパー動的URL | 初期／VIP選択／再クリック解除／スペシャル選択すべて `HANDOFF.md` 3-2 の表どおり |
| DMリンク | `https://ig.me/m/estmiki` ✅ |
| `lp/index.html` | **無変更**（`git diff` で確認） |

⚠ **ヘッドレス撮影では `loading="lazy"` の画像が空白に写る。** ヘッドレスはスクロールしないため。
表示の前後比較をするときは検証サーバの `?nolazy=1` を使うこと。**これは撮影上の問題で、
実ブラウザでは正常に読み込まれる。**

### build_site.py が「止まる」条件

Codexレビューを受けて、**静かに壊れるより落ちる**ように作ってある。
ビルドが止まったらこの表を見ること。

| メッセージ | 意味・直し方 |
|---|---|
| `外部化できなかった data URI が残っている` | `DATA_URI_RE` が拾えない形式が増えた。サブタイプ（`svg+xml` 等）か改行入りbase64を疑う |
| `<img> の抽出数が合わない` | `IMG_TAG_RE` が想定外の書き方に当たった。引用符なし属性に `>` がある等 |
| `OGP画像の元になる --concept-img が見つからない` | `lp/index.html` のCSS変数名が変わった。**フォールバックは意図的に置いていない**（口コミスクショが黙ってOGPになる事故を防ぐため） |
| `site.json の "url" は末尾に / が必要` | 末尾スラッシュを落とすと `…workers.devogp.jpg` のような壊れたURLが**エラーなく**できる |
| `indexnow_key が不正` | キーはファイル名になるので `/` や `..` を弾いている |

その他レビュー由来の実装上の注意：

- **`<img>` の抽出に `[^>]*` を使わないこと。** `alt="A > B"` のような属性値で切れて属性を壊す。
  しかも `<img` の個数とは一致するので件数チェックでも検知できない
- **JSON-LD は `</` を割ってから埋め込む。** `json.dumps` は `</script>` をエスケープしない
- **`sitemap.xml` の `lastmod` はビルド日ではなく入力の内容ハッシュで決める。**
  毎回日付が進むとクローラへの更新シグナルが濁る（`site.json` の `_source_hash` に記録）
- **`_headers` のセキュリティヘッダは `/*` に置く。** `/` だけだと画像・404・robots に掛からない

---

## 8. 保留事項（公開はブロックしない・ユーザー確認済み）

- **CTA文言の食い違い**：LP「MIKI指名 20%OFF・VIPコース(150分/180分)限定」 vs
  投稿「MIKI指名 初回限定20%OFF（VIPコースのみ）」→ **保留のまま公開でOK**
- **サロン名 / LocalBusiness / Googleビジネスプロフィール** → **保留のまま公開でOK**
- **口コミNo.1 の根拠待ち**：現在「20・30代のお客様に ご好評」に退避済み、"No.1" はページ内0件。
  このまま公開して問題ない
- **独自ドメイン**：Workers なら後から追加できる。ただし**URL変更時はリダイレクト設定と
  Search Console の再登録**が必要なので、切り替えるなら早いほど傷が浅い

---

## 9. ダッシュボードと投稿プレビューの noindex（対応済み）

内部向けのAIダッシュボードと投稿プレビュー**21件**が GitHub Pages で誰でも開ける状態だった
（実測で確認）。LPをSearch Consoleに登録するとGoogleが同一サイト内を探しに来るため、
先に塞いだ。

| 対象 | ファイル |
|---|---|
| ダッシュボード（**ソース・ここが正**） | `dashboard/index.html` |
| ダッシュボード（現物の即時パッチ） | `docs/index.html` |
| 投稿プレビュー（今後の生成分） | `register_post.py` の `generate_preview_html()` |
| 投稿プレビュー（既存22件） | `docs/*/index.html` |

⚠ **robots.txt では防げない。** GitHub Pages のプロジェクトページはサブパス配信で、
robots.txt が読まれるのは `spikesukeshun.github.io` 直下＝別リポジトリの管轄（現在404）。
**meta robots が唯一の手段。**

⚠ **`docs/index.html` を直接直してもダッシュボードの週次ビルドで巻き戻る。**
`dashboard/index.html`（Viteのソース）が正。

⚠ noindex は**検索結果に出さないだけ**で、URLを知る人は引き続き開ける。非公開にはならない。
