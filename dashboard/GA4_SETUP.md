# GA4 / Search Console 連携のセットアップ

ダッシュボードのファネルを「プロフィール閲覧 → **LP訪問** → **予約導線クリック** → 予約」まで
実数でつなぐために、GA4とSearch Consoleを週次更新に載せる。`dashboard/fetch_ga4_data.py` が使う。

**この手順は美喜さんの操作が必要**（Google Cloud のサービスアカウント作成）。
一度やれば以降は自動。所要10〜15分。

> ⚠ 未設定でもダッシュボードの週次更新は従来どおり動く。LPのセクションが出ないだけ。
> Instagram側の更新を巻き添えにしない作りにしてある。

---

## 1. Google Cloud でサービスアカウントを作る

1. https://console.cloud.google.com/ を開く（GA4と同じ `s.bsb.o.s1@gmail.com` でログイン）
2. 画面上部でプロジェクトを選ぶ。無ければ「新しいプロジェクト」→ 名前は `miki-dashboard` など
3. **APIを有効化**（2つ）
   - 「APIとサービス」→「ライブラリ」→ `Google Analytics Data API` を検索 →「有効にする」
   - 同じく `Google Search Console API` を検索 →「有効にする」
4. **サービスアカウント作成**
   - 「IAMと管理」→「サービスアカウント」→「サービスアカウントを作成」
   - 名前: `miki-dashboard-reader` / ロールは**付けなくてよい**（GA4側で権限を渡すため）
   - 「完了」
5. **JSONキーをダウンロード**
   - 作ったサービスアカウントをクリック →「キー」タブ →「鍵を追加」→「新しい鍵を作成」→ **JSON** → 作成
   - ファイルがダウンロードされる。**このファイルがパスワードそのもの**なので扱いに注意

6. **サービスアカウントのメールアドレスを控える**
   `miki-dashboard-reader@<プロジェクトID>.iam.gserviceaccount.com` という形。次で使う。

---

## 2. GA4 と Search Console に「閲覧者」として招待する

⚠ ここを飛ばすと `HTTP 403` で失敗する。鍵を作っただけでは何も見られない。

**GA4**
1. https://analytics.google.com/ →「管理」→ プロパティ設定「プロパティのアクセス管理」
2. 右上「＋」→「ユーザーを追加」
3. 上で控えたサービスアカウントのメールアドレスを入力
4. 役割は **「閲覧者」**（それ以上は不要）→「追加」

**Search Console**（検索クエリも取りたい場合のみ。省略可）
1. https://search.google.com/search-console/ → プロパティ `https://www.esthe-miki.workers.dev/`
2. 「設定」→「ユーザーと権限」→「ユーザーを追加」
3. 同じメールアドレス / 権限は **「制限付き」** →「追加」

---

## 3. 鍵を安全な場所に置く

**リポジトリの中に置かないこと**（GitHubに上がると第三者がGA4を読めてしまう）。

```bash
mkdir -p ~/.config/miki-dashboard
mv ~/Downloads/<ダウンロードしたファイル>.json ~/.config/miki-dashboard/ga4-service-account.json
chmod 600 ~/.config/miki-dashboard/ga4-service-account.json
```

---

## 4. 環境変数を `~/.zshrc` に追記

このプロジェクトは `load_env.py` が `~/.zshrc` を読む方式。`.env` ではなくこちらに書く。

```bash
export GA4_PROPERTY_ID="549776757"
export GOOGLE_APPLICATION_CREDENTIALS="$HOME/.config/miki-dashboard/ga4-service-account.json"
export SEARCH_CONSOLE_SITE_URL="https://www.esthe-miki.workers.dev/"
```

- `GA4_PROPERTY_ID` は GA4のURL `analytics.google.com/.../a404550589p549776757` の
  **`p` の後ろの数字**。`a` の後ろ（アカウントID）ではないので注意
- `SEARCH_CONSOLE_SITE_URL` は**末尾スラッシュまで含めて**Search Consoleの登録どおりに書く
  （URLプレフィックス型のプロパティなので1文字でも違うと404）

追記したら新しいターミナルを開く（または `source ~/.zshrc`）。

---

## 5. 動作確認

```bash
/usr/bin/python3 dashboard/fetch_ga4_data.py
```

成功すると週別・参照元別のJSONが表示され、最後に

```
✅ 3週分 / セッション84（うちInstagram経由37） / cta_hotpepper 65
```

のような行が出る。

### よくある失敗

| 症状 | 原因と対処 |
|---|---|
| `GA4_PROPERTY_ID が未設定です` | `source ~/.zshrc` を忘れている／新しいターミナルを開く |
| `HTTP 403` | 手順2をやっていない。GA4のアクセス管理にサービスアカウントを追加する |
| `HTTP 404`（Search Consoleだけ） | `SEARCH_CONSOLE_SITE_URL` の綴り。末尾スラッシュ・`www.` の有無を登録と一致させる |
| `queries` が空配列 | 異常ではない。表示回数が少ないとGoogleがクエリを匿名化して返さない |
| セッション数が実際より多い | 海外からの自動化アクセスが混ざっている。参照元/メディア別の `sources` で切り分ける |

---

## 取得している内容

| 区分 | 中身 |
|---|---|
| `weeks[]` | 月曜始まりJSTの週別。セッション・エンゲージ数・平均滞在秒・CTAクリック数。<br>`instagram_*` はInstagram経由だけを抜いたもの |
| `sources[]` | 参照元/メディア別の合計。**どれが実ユーザーでどれが自動化アクセスかを見分ける行** |
| `search_console` | 表示回数・クリック・平均掲載順位・上位クエリ |

⚠ **チャネルグループ（Organic Social など）ではなく参照元/メディアで持っている。**
チャネル粒度だと `instagram / (not set)` と `instagram / social` の分断や、
自動化アクセスが多い `(direct) / (none)` との混同が起きて誤診する（2026-08-30に実際に誤診した）。
