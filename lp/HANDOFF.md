# MIKI サロン LP — 引き継ぎ

最終更新: 2026-08-12

## 1. 成果物

| 項目 | 値 |
|---|---|
| ソース | `/Users/shunsuke/Desktop/美喜のinstagram/lp/index.html`（単一ファイル・310KB） |
| 公開URL | https://claude.ai/code/artifact/0339725a-6a87-493d-b337-dd920153489f |
| git | ブランチ **`lp/conversion-landing-page`** にコミット済み（初回コミット `ddcec57`）。**push はしていない** |

### ⚠️ 更新時の必須手順
別セッションから更新する場合、Artifact ツールに **`url` パラメータで上記URLを渡すこと**。
渡さないと**新しいURLが発行され、既存リンクが更新されない**。

```
Artifact(file_path: ".../lp/index.html",
         url: "https://claude.ai/code/artifact/0339725a-6a87-493d-b337-dd920153489f",
         favicon: "🌿", description: "...")
```
favicon は 🌿 で固定（変更するとタブの見た目が変わり別ページに見える）。

---

## 2. 未解決タスク（次セッションの主目的）

### A：口コミNo.1 の根拠待ち
- ユーザー談：「インスタ側のプロフィール欄は修正します。LP側については根拠を追って送ります」
- **現在LPは「20・30代のお客様に ご好評」に変更済み**（"No.1" はページ内 0件）。
- 根拠が届いたら `20・30代 口コミNo.1（〇〇調べ／2026年◯月／六本木エリア◯店舗中）` の形で戻せる。**調査主体・時期・範囲の併記が必須**（景表法対策）。
- 該当箇所：`.trust-list` の1項目目。

### 保留中の確認事項
- **カルーセル投稿側のCTAスライド**は CLAUDE.md の恒久ルールで「MIKI指名 初回限定20%OFF（VIPコースのみ）」固定。
  LPは「MIKI指名 20%OFF ・ VIPコース(150分/180分)限定」表記のため**不一致**。投稿側も揃えるならCLAUDE.md更新が必要（ユーザー未回答）。
- **プロフィール写真だけプレースホルダーのまま**。候補 `miki.JPG` / `miki.jpg` は指差し・両手を広げた笑顔＋赤い花柄バックで、
  明朝＋オリーブの世界観と方向が違うためユーザー判断で**意図的に未挿入**。落ち着いたポートレートが用意でき次第入れる。
- ヒーローの `メニューを見る` は2つの予約ボタンと同じ `.cta-row` 内にある（375pxでは3行に折り返す）。ボタン文言を長くする場合は折り返しを再確認すること。

### 解決済み（2026-08-06）
- オイル系3メニュー（リラクゼーション/経絡/リラスリム）は**LPから削除**。ホットペッパーのクーポン3種に差し替えたため、平日割の有無・価格逆転の論点は消滅。

## 3. 確定済みの料金（LP実装値）

すべて税込。**指名料+1,000円は表示価格に含まれない**（LP内3か所で明記済み）。

| コース | 平日 | 土日祝 | 備考 |
|---|---|---|---|
| VIP 150分 | **19,040**（20%OFF後） | 19,840（20%OFF後） | 元値 平日23,800 / 土日祝24,800 |
| VIP 180分 | **22,240** | 23,040 | 150分＋30分オプション |
| ＋30分オプション | **＋3,200**（20%OFF後） | ＋3,200 | 元値+4,000。平日休日とも同額 |
| スペシャル 120分 | **14,800** | 15,800 | |
| インディバ×首肩コリ 95分 | **14,800** | 15,800 | |
| 【バースデー特典】心と体を満たす贅沢 150分 | **17,800** | 18,800 | |
| 【星座別アロマ】星の導きと香りの癒し 60分 | **6,980** | 7,980 | |

全コース「平日は土日祝より1,000円オフ」が成立している。

**20%OFFの条件**：**VIPコース(150分/180分)のみ** ・ MIKI指名 ・ Instagramフォロー。
→ item5対応として、LP内4か所（ご予約の前にボックス／スペシャルカードのCTA脇／FAQ／フッター注記）で「VIP限定」を明示済み。

---

## 3-2. 予約導線（2026-08-06 全面改定）

**優先順位：1. DMから相談する ／ 2. ホットペッパーから予約する**

- **DMリンクは `https://ig.me/m/estmiki`**（Instagram公式のDMディープリンク。302→`instagram.com/m/estmiki`。アプリがあればDM画面が直接開く）。
  プロフィールURL `instagram.com/estmiki/` を使うのは**フッターのアカウントリンク1箇所のみ**。
- **ホットペッパーのリンクは選択中コースで動的に切り替わる**。
  - 対象は `data-hp-target` 属性を持つアンカー（ヒーロー／選ばれる理由／メニュー下／流れ／最終CTA／固定ドック の6本）。
  - JSの `HP_DEFAULT` が未選択時のURL。各コースカードの `data-hp` 属性が選択時のURL。
  - VIP・スペシャルカード内のCTAだけは**自コースのクーポンURL固定**（動的対象外）。

| 選択状態 | URL |
|---|---|
| 未選択（初期状態） | `.../reserve/?storeId=H000075398&staffId=W000048120` |
| VIPコース | `.../reserve/afterCoupon?...&couponId=CP00000009971204&add=0` |
| スペシャルコース | `...&couponId=CP00000008015550&add=0` |
| インディバ×首肩コリ | `...&couponId=CP00000012928170&add=0` |
| バースデー特典 | `...&couponId=CP00000010821510&add=0` |
| 星座別アロマ | `...&couponId=CP00000012584055&add=0` |

- **メニューは選択解除できる**（同じカードを再タップで解除→未選択URLに戻る）。
  カード内のCTAリンクを踏んだ場合は**解除せず選択を維持**する（`selectCard(card, allowToggle)` の第2引数）。
- **初期状態は「未選択」**（改定前はVIPが選択済みだった）。ドックは「コースをお選びください／未選択のままでもご予約いただけます」を表示。
- ホットペッパー予約の注意事項3点（Instagramフォロー必須／当日「インスタ見たよ」／限られた時間での対応となる場合あり）は
  **ご予約の前にボックス・最終CTA下・FAQ** の3か所に記載。

## 4. 実装済み機能

- **構成**：ヒーロー → 実績バー → 共感 → オリーブ地コンセプト → 選ばれる理由 → Before/After → メニュー&料金 → 口コミ → 流れ → FAQ → アクセス → プロフィール/最終CTA → フッター
- **CTAリンク先**：上記「3-2. 予約導線」参照。
- **DM下書きコピー**：`[data-tmpl]` のアンカー2本（メニュー下・最終CTA）。クリックで定型文をクリップボードにコピーし、そのままDMを開く。
  選択中コースがあれば文面にコース名が入る。**コピーは同期処理necessary**（アンカーが直後に遷移するため、`navigator.clipboard` の非同期完了を待てない）→ `textarea`+`execCommand('copy')` を主、Clipboard API を併用。
  **⚠ Instagram の `ig.me` には本文プリセットのパラメータが存在しない**（WhatsApp の `wa.me/?text=` 相当は無い）。文面を用意した状態でDMを開かせたい場合は、Instagram側の「よくある質問（アイスブレイカー）」設定を使うしかない。
- **Instagramプロフィールリンク**：2箇所。
  1. `.ig-link`（アイコン＋＠estmiki＋説明＋矢印）＝ MIKIプロフィール欄。
  2. `.head-ig`（丸いアイコンのみ）＝ ヘッダー、「DMから相談」の左。`.head-actions` で2つをgap:10pxの組にしている。

- **ヘッダーナビ（2026-08-07 変更）**：選ばれる理由／メニュー／お客様の声／アクセス／**プロフィール** の5本。フッターナビにも プロフィール を追加して揃えた。
  **⚠ nav-link を隠すブレークポイントを 760px → 900px に上げてある**。5本＋アイコン＋CTAだと `brand(87)+nav(659)+padding*2` で
  **約860px を下回るとヘッダーが溢れる**ため。`.head-nav` の gap も 30 → 26 に詰めた。
  **ナビ項目を増やす／ラベルを長くする場合は、このブレークポイントを必ず再計算すること**（901/1000/1280で収まり、899/800/500で非表示になることを検証済み）。

- **モバイル用セクションレール `.rail`（2026-08-07 追加）**：900px以下でだけ表示される右端固定のドットナビ（ヘッダーナビと同じ5項目）。
  ヘッダーナビと**排他**（`@media (max-width:900px)` で rail を表示、同じ条件で nav-link を非表示）。**片方を変えたら必ずもう片方も合わせること**。
  - スクロール連動：各セクションの `top <= 140` を満たす**最後の**要素をアクティブにする。ページ最上部ではどれも点灯しない（正常）。
  - ラベルは**区間が変わった直後 1.9 秒だけ**表示して畳む。常時表示にすると本文を最大101px覆うため。`.rail.show-label` で制御。
  - **スクロールハンドラは rAF ではなく時間スロットル（90ms）**。rAF だとフレームが止まる環境で更新されず検証もできない。
    そのため**同期的にテストするときは dispatchEvent の間に120ms以上のウェイトが必要**（連続で撃つとスロットルに吸われて「効いていない」ように見える）。
  - z-index は `rail 55 < dock 70 < lightbox 100`。ドックとは縦位置が重ならない（レールは上下中央）。
  - **既知のトレードオフ**：タップ領域が本文右端に5px重なる。Before/Afterスライダーの右端5pxはレール側が取る。
    `right` / `padding-left` を広げるとこの重なりが増えるので注意。
  ヒーロー・最終CTAには置かない（予約導線からの離脱を避けるため）。
  **アイコン単体が許されるのはヘッダーだけ**（定位置＋Instagramのグリフは周知のため）。`aria-label`/`title` は必須。
  本文中に置く場合は用途が伝わらずCTRが落ちるので必ずテキストを併記すること。
- **メニュー単一選択＋解除**：`[data-price]` の5枚（VIP/スペシャル/その他3種）。選択でゴールドの2px枠。「迷ったら」カードは選択対象外。
- **メニュー欄の並び（2026-08-07 変更）**：コース比較図 → **「料金の見かた」** → VIPカード → スペシャルカード → その他3コース → **「ホットペッパーからご予約の方へ」** → 予約ボタン。
  **全ブロックが同じ幅**（`.narrow` 幅いっぱい）。旧 `.price-duo` の2カラムグリッドは廃止。
  旧「ご予約の前に」1枚を **2枚に分割**した。理由：料金ルール（税込・平日割・指名料・20%OFFはVIP限定）は**価格を見る前**に効き、
  ホットペッパーの条件（フォロー・インスタ見たよ・時間制限）は**予約ボタンの直前**で効くため。1枚にまとめて上に置くと、
  価格を1つも見ないうちに※が9行並んで失速し、かつ予約経路の話だけ文脈から浮く。
- **固定CTAバー**：選択中メニュー名＋条件を常時表示（`#dockName` / `#dockMeta`）。DM(金)＋ホットペッパー(白)の2ボタン。
  640px以下ではテキストが上段・2ボタンが下段に折り返す。スクロール方向で拡縮。
- **その他**：Before/After比較スライダー、口コミカルーセル、FAQアコーディオン、画像ライトボックス、reveal/パララックス
- **埋め込み画像**（base64 data URI）：蓮エンブレム(VIP)・葉エンブレム(スペシャル)・コース比較カード・アクセスマップ・Before写真・After写真 の6点＋**口コミスクショ11点**（4-3）

### 4-2. Before / After（2026-08-07 追加）

**⚠ Drive のファイル名と LP 上の割り当ては逆**（ユーザー確認済み・意図的）:

| Drive のファイル名 | 写っている状態 | LP上 |
|---|---|---|
| `after photo-output.HEIC` (`1Og8AB3QjADIjEJF4vZyA0a6JxevoYE0Q`) | 体格が大きい | **Before** |
| `before photo-output.HEIC` (`1y1Clla9MoR1VkEZLjlK4U3ZwE0PnWV_X`) | 細い | **After** |

- どちらも 3352/3277px の**正方形**。1400x1400 / JPEG q88 に変換して埋め込み（合計 約390KB）。
  これに伴い `.ba-wrap` を `aspect-ratio:4/3 → 1/1`、`max-width:720px → 560px` に変更。
- **2枚の撮影倍率は同一であることを検証済み**：両方に写り込んでいる壁のインターホンでテンプレートマッチ（NCC 0.805 / scale 1.01）。
  拡大率の差による誇張はない。**別の写真に差し替える場合は同じ検証をすること**（倍率が違うと変化が実際より大きく見え、景表法上のリスクになる）。
- **色味を揃える補正を適用済み（2026-08-07）**。補正前は After（細い方）が明るさ+14%・色も中立で、**Afterが有利になっていた**。
  壁（同一の被写体）を基準に、2枚の壁の幾何平均へ**両方を寄せる**per-channelゲインを適用。補正後は両方とも壁が R/G=1.116 / B/G=0.850 / 輝度180.4 で一致。
  **触ってよいのはホワイトバランスと露出だけ**。肌の滑らかさ・体型の補正は絶対にしない（優良誤認になる）。
  補正スクリプトの考え方：`wall_rgb()` で左上コーナーの上位30%輝度画素を壁とみなし、`target=sqrt(wallA*wallB)`、各画像に `target/wall` を乗算。
- スライダー下に **結果ストーリー（`.ba-story`）** を追加：「半年で −12kg」＋月2回の施術・自宅でのゆるい運動/食事改善・3〜6ヶ月周期・変化3項目。
  出典はユーザー提供の過去Instagram投稿。LPには絵文字を入れない方針のため 🌿 は落としてある。
- **注記の文言**：「画像はイメージです」は実写真と矛盾するため廃止。
  `.ba-note` は「実際のお客様の一例／約6ヶ月・月2回の施術＋自宅でのゆるい運動と食事改善／個人差あり・施術のみで同じ結果を保証しない」を明記。フッター注記も同様に修正済み。

### 4-3. お客様の声＝口コミスクショ（2026-08-12 全面差し替え）

作られた短いコピー4枚をやめ、**ホットペッパービューティーの口コミ画面のスクショ11枚**に置き換えた。

- **元データ**：Drive フォルダ `口コミ`（ID `1_0VnegnMva6fYk25JHzxz76omBa8qlgA`）に43枚。`drive_manager.py` の
  service account でそのまま読める（テーマフォルダではないので `drive_folders.json` には無い）。
- **採用基準**：ユーザー指定で**文章量の多い順**。文章量は本文の描画高さ（＝行数×54px）で機械的に測る。
  588px以上の11枚を採用。同数は投稿日の新しい順。12位以下は534pxが8枚並ぶのでここが自然な区切り。
- **再生成の手順**：Drive から `kuchikomi/` に落とす → `lp/tools/normalize_reviews.py`（出力 `normalized/`）
  → `lp/tools/embed_reviews.py`（`REVIEWS` の並びがそのまま掲載順）。どちらも実行ディレクトリ直下の相対パスを見る。
- **正規化**（`lp/tools/normalize_reviews.py`。仕様を変えるときはこの節ごと直すこと）:
  - 上端＝「（女性/30代…）」行の**直上**で切る。元スクショにはアバターアイコンの下端が数px写り込んでいて、
    その残り方が画像ごとに違うのが「サイズがバラバラ」に見える主因だった。行の上38pxは、
    **文字行と紫の区切り線の間にある無地の帯をそのまま移植**して作る。
    1行を複製して埋めると**JPEGのブロックノイズが縦に伸びて筋になる**（一度これで失敗した）。
  - 下端＝「予約時のクーポン・メニュー」枠の下罫線。`IMG_9584` / `IMG_3854` は罫線ごと切れているので3pxの罫線を合成する。
  - 左右＝カードの枠線でトリミング → **幅1158pxに統一**（元は1206/1179/1160pxの3種。フォントの実pxは共通なので幅を揃えれば文字サイズも揃う）。
  - `IMG_0109` は**右端が約17px切れている**。本文は x<1145 に収まっているので、背景列を複製して余白と枠線を再構成した。
  - `IMG_0085` / `IMG_0093` / `IMG_0105` に **PAGETOPボタン**（半透明グレー）が写り込んでいる。
    白地に重なった実測色から逆合成して除去する（下地が透ける割合 **0.318**、ベタ塗り部分の実測色から係数を出す）。
    `IMG_0105` はメニュー文字の上に重なっているが、逆合成なので**文字は完全に復元される**。
    「^」と「PAGETOP」の白字だけは淡い輪郭として残るので、濃い画素から離れた淡い画素を白に飛ばして消す。
  - 出力は **WebP q80**。11枚で約775KB → base64 約1.04MB、`index.html` 全体で **2.7MB**。
    JPEGだと base64 2.16MB になるので WebP を使うこと。
- **表示**：文章量順に並べたので**スライドを送るほど高さが縮む**。`.carousel-view` の高さを
  現在のスライドに追従させている（`fit()`）。追従は `ResizeObserver` で行う。
  **`resize` イベントだけでは足りない**（画像デコードやフォント差し替えの後に高さが取り残される）。
- **自動送りは廃止**。長文の口コミを5.2秒で送ると読めない。矢印・ドット・スワイプのみ。
- `.vcard` は `<figure>` なので **`margin:0` が必須**。UAデフォルトの `margin:1em 40px` を放置すると
  スライドが右に40pxずれて画像の右端が切れる（元の短いコピーでは中央寄せで見えていなかった）。
- **ライトボックス（`[data-zoom]`）には繋いでいない**。`.lb-box` は `min(640px,92vw)`・`overflow:hidden` 固定なので、
  縦1700pxの画像を入れると破綻する。
- **注記**（`.ba-note` を流用）：「ホットペッパービューティーに投稿された口コミをそのまま掲載／感想には個人差があり、
  同じ結果を保証するものではない」。`IMG_9584` に「1ヶ月で4キロも痩せる」、`IMG_0095` のクーポン名に「人気No.1」が
  含まれるため**必須**。Before/After の注記（4-2）と同じ考え方。

### ブランドルールの例外（重要）
- 原則「AMRTA」サロン名は非表示。**ただしアクセスセクションのみユーザー判断で例外**。
  - マップはサロン名入りの**Drive原本 `map.jpg` をそのまま使用**（一度マスクしたが差し戻し済み）
  - 住所見出しは「**アムリタ 六本木 / AMRTA**」表記

---

## 5. 検証方法（重要・ハマりどころ）

### 制約
- `lp/index.html` には **`<!doctype>` / `<head>` / `<body>` が無い**（Artifact公開時にskeletonが付与される仕様）。
- そのため**生ファイルをそのままブラウザで開くとquirksモードになり、`body{overflow-x:hidden}` でスクロールが壊れる**。ローカル検証は必ず下記サーバ経由で行う。
- CSP：外部CDN/フォント/画像/iframe/fetch すべて不可。CSS/JSはインライン、画像はdata URIのみ。

### 検証用サーバ（scratchpadに再作成して使う）
```python
import http.server, socketserver, urllib.parse
D = "/Users/shunsuke/Desktop/美喜のinstagram/lp/index.html"
HEAD = ('<!doctype html>\n<html lang="ja">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n</head>\n<body>\n')
TAIL = """
<style>[data-reveal]{opacity:1!important;transform:none!important}
.hero .rise{opacity:1!important;animation:none!important;transform:none!important}</style>
<script>document.querySelectorAll('[data-reveal]').forEach(function(e){e.classList.add('in')});
document.documentElement.style.scrollBehavior='auto';</script></body></html>"""
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        tall = q.get("tall", [None])[0]
        body = open(D, encoding="utf-8").read()
        tail = TAIL
        if tall:  # 100svh のヒーローを固定化して全ページ撮影を可能にする
            tail = '<style>.hero{min-height:%spx!important;height:%spx!important}</style>' % (tall, tall) + tail
        data = (HEAD + body + tail).encode("utf-8")
        self.send_response(200); self.send_header("Content-Type","text/html; charset=utf-8")
        self.send_header("Content-Length",str(len(data))); self.send_header("Cache-Control","no-store")
        self.end_headers(); self.wfile.write(data)
    def log_message(self,*a): pass
with socketserver.TCPServer(("127.0.0.1",8128), H) as s: s.serve_forever()
```

### ⚠ ヘッドレスChromeは375pxを再現できない
`--window-size=375,812` を指定しても **innerWidth は 500 に丸められる**（`--force-device-scale-factor` を変えても同じ）。
そのため「モバイルで要素がはみ出している」ように見えるスクリーンショットは**偽陽性**。
**真の375px検証は in-app ブラウザの `resize_window(preset:"mobile")` + `javascript_tool` で行うこと**（こちらは正しく375pxになる）。

### スクリーンショット（in-appプレビューは不安定）
`mcp__Claude_Browser__computer` の scroll/screenshot は**このページでハングまたは空白になる**。
代わりに **ヘッドレスChromeで全ページを1枚撮り、PILで切り出す**：
```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --disable-gpu \
  --hide-scrollbars --force-device-scale-factor=1 --run-all-compositor-stages-before-draw \
  --virtual-time-budget=20000 --window-size=1180,12000 \
  --screenshot=out.png "http://localhost:8128/?tall=860"
```
オリーブ色 `rgb(85,96,74)` の帯を検出するとVIPカード位置を特定できる。

### 機能検証はJSで同期的に
`mcp__Claude_Browser__javascript_tool` は動作する。`requestAnimationFrame` 依存の検証は**paneのframe loop停止でハングする**ので避け、同期的にDOM/クラス/テキストを読む。
必ず確認する項目：モバイル375pxで `document.documentElement.scrollWidth > innerWidth` が false（横溢れなし）。

---

## 6. Drive素材の取り方

`drive_manager.py`（mainリポジトリ）を使用。`list_drive_images(theme)` / `download_drive_image(file_id, dest)`。
テーマキー：`menu`（施術・メニュー紹介）/ `bridal` / `reward`。

使用中のファイルID：
- コース比較カード `コース2種類`：`1b4kIZCMTdbbQMKb1hzPO15exi8UAI0bk`
- VIPバナー（蓮エンブレム抽出元）`VIPコース②`：`1-wbFyAu232oMZME-MUm12eddAWKrN90L`
- スペシャルバナー（葉エンブレム抽出元）`スペシャルコース②.jpg`：`18AQQXXO2URzyb7AvWIvZQIKFckXlT2hK`
- アクセスマップ `map.jpg`：`1vkDgAh11Rya-5Dz3lIoBxzTgyQiIdI9D`

注意：Mac由来のファイル名は**NFD正規化**されており手打ち文字列と一致しない。名前照合するときは `unicodedata.normalize` を通すか、上記IDを直接使う。
`assets/miki_bubble.png` は**ロゴではなくMIKI本人の顔写真**。ブランドマークの実体はコースカードのゴールドのエンブレム。

---

## 7. デザイントークン（変更時は必ず踏襲）

```
--bone:#FBF8F2  --cream:#F4EDE1  --sand:#E6D9C4
--olive:#55604A（構造色・VIPカード/コンセプト/フッター）  --olive-2:#6E7A5B  --sage:#98A084
--wood:#8A6F57  --gold:#B08A46  --gold-deep:#8C6D33（CTA塗り）  --ink:#2C2723
見出し=明朝（Hiragino Mincho ProN系）／本文=Hiragino Sans系／欧文ラベル=Optima系
```
- CTAアクセントはページ全体で**ゴールド1色に統一**（要件）。
- **単一ライトデザインに意図的にコミット**（`color-scheme:light` 固定。dark設定の閲覧者にも暖色のまま見せる）。


---

## 8. 実写真の投入とカードのポップアップ（2026-08-08）

### 8-1. 使用写真（すべて Drive「施術・メニュー紹介」→ data URI 埋め込み）

| 用途 | Driveファイル名 |
|---|---|
| ヒーロー背景 | `サロン`（同名2件のうち**ベッド2台が写っている方**） |
| コンセプト | `Droom.JPG` |
| 理由01 リンパを流す | `お腹のマッサージ 1.JPG` |
| 理由02 むくみを解消 | `施術写真背中` |
| 理由03 代謝を上げる | `ラジオ波施術` |
| Step01 カウンセリング | `サロン`（**窓と椅子の待合**が写っている方） |
| Step02 ジャグジー | `jacuzzi.JPG` |
| Step03 施術 | `head massage.JPG` |
| Step04 アフタータイム | `herbs.JPG` |

**⚠ 使ってはいけないもの**（写真ではなく**広告バナー**）:
`ドリンク`（もろみ酢の商品広告）/ `キャビテーション`（機器の仕組み図）/ `menu_dead_sea_bath_salt`（販促バナー）。
名前から中身を推測せず、**必ず目視してから使うこと**。

ユーザー確認済みの方針：**AMRTAロゴの写り込みは許容**（`サロン`の待合カット等）。**施術写真の顔の写り込みも掲載可**（許諾済み）。

### 8-2. モーダルは2モード共用

`#lb` を画像モード（`[data-zoom]`）と文章モード（`[data-modal]`）で共用している。詳細の中身は
`.modal-src[hidden]` としてフッター付近に7枚分置いてある（理由3枚＋流れ4枚）。

- **PCは横並び**（`@media (min-width:641px)` で `display:flex`、写真43%）。
  縦積みのままだと写真(16:10)だけで376px使い、**7枚とも約140px溢れる**。
- 高さ上限は `calc(100svh - 64px)`。**`86vh` のような比率指定に戻すと背の低い端末（375×667）で溢れる**。
- **文章量を増やすときは 375×667 と 1280×800 の両方で再測定すること**（`scrollHeight - clientHeight` が0）。
- フォーカスは閉じるボタンとモーダル内リンクを循環する（画像モードは閉じるのみ）。

### 8-3. 文言の統一ルール

- ナビ／レール／フッター＝**「変わる理由」**、見出し＝「からだが変わる、3つの理由」
- **ジャグジー15分は全コース共通**。「VIP・スペシャルのみ」と書かない
- ホットペッパー割引は**2条件そろって初めて適用**（Instagramフォロー＋当日「インスタ見たよ」）。`.cond` ボックスで番号付き表示し、
  「どちらか一方でも欠けると通常料金」を明記している
- ヒーローのリード文（`.hero-eyebrow`）は**文字色と罫線を同色**にする（`--gold-deep`）。
  `.kicker::before` の既定は `--gold` なので、`::before` 側も上書きしないと色がずれる

### 8-4. 写真の縁は mask ではなく重ねグラデーション

`mask-image` は実ブラウザでは効くが**ヘッドレスで合成されず検証できない**。そのため
`.hero-photo` / `.concept-photo` は**4辺のグラデーションを重ねる方式**にしてある。maskに戻さないこと。
なお `radial-gradient` 1枚では**辺の中央まで届かず角だけ暗くなる**ので、4辺個別の `linear-gradient` を使っている。

### 8-5. 検証環境のクセ（追記）

- in-app ブラウザは**フレームループが止まりCSSトランジションが進まない**。モーダルの可視状態を伴う検証は
  `.lb{transition:none}` `.lb.on{opacity:1;visibility:visible}` を注入してから測る
- ローカル検証サーバのプロセス名は `python3 serve.py`。**`pkill -f "scratchpad/serve.py"` では止まらない**。
  `lsof -ti tcp:8128 | xargs kill -9` を使う（古いプロセスが残ると `?modal=` 等の新しいクエリが効かない）
