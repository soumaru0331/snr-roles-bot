# Super New Roles 役職検索 Discord Bot — 設計書

**日付:** 2026-05-06  
**ステータス:** 承認済み

---

## 概要

Super New Roles（アモングアスMod）の役職をDiscord上で簡単に調べられるBotを作成する。  
Wikiから全役職データを取得し、ボタンUIと検索コマンドで誰でも素早く役職情報を確認できるようにする。

---

## アーキテクチャ

### ファイル構成

```
bot among/
├── bot.py              # メインBot（コマンド・UI・スケジューラー・Webサーバー）
├── requirements.txt    # 依存パッケージ
├── roles_cache.json    # スクレイピング結果キャッシュ（自動生成・gitignore対象）
├── discord token.txt   # Discordトークン（既存）
├── .env               # 環境変数（Renderデプロイ用）
├── Procfile           # Render起動設定
├── runtime.txt        # Python バージョン指定（python-3.11.x）
└── docs/
    └── superpowers/specs/
        └── 2026-05-06-snr-roles-bot-design.md
```

### データフロー

```
Wiki HTML → BeautifulSoup → roles_cache.json → Discord Embed
                                  ↑
                       APScheduler（毎日UTC 0:00 に自動更新）
```

### 使用ライブラリ

| ライブラリ | バージョン | 用途 |
|---|---|---|
| `discord.py` | 2.x | Discord Bot本体・スラッシュコマンド・View/Button UI |
| `beautifulsoup4` | 最新 | WikiページのHTMLパース |
| `requests` | 最新 | WikiページのHTTP取得 |
| `apscheduler` | 3.x | 定期スクレイピング（1日1回） |
| `jaconv` | 最新 | ひらがな↔カタカナ↔ローマ字変換（検索用） |
| `flask` | 最新 | UptimeRobot ping受け用最小Webサーバー |

---

## 機能仕様

### スラッシュコマンド

| コマンド | 引数 | 動作 |
|---|---|---|
| `/roles` | なし | 陣営選択ボタンを表示 |
| `/search` | `keyword: str` | キーワードで役職を直接検索 |

### `/roles` UI フロー

```
/roles
  └→ 陣営選択ボタン行
       [クルーメイト] [インポスター] [ニュートラル] [その他]
       └→ 陣営ボタン押下
            └→ 役職一覧（10件/ページ）＋ [◀前へ] [次へ▶] ページネーション
                 └→ 役職名ボタン押下
                      └→ 役職詳細 Embed 表示
```

### `/search <keyword>` 検索仕様

部分一致で以下すべての入力形式に対応する：

| 入力例 | マッチ例 |
|---|---|
| `イビルゲ` | イビルゲッサー |
| `いびるげ` | イビルゲッサー |
| `ibiruge` | イビルゲッサー |
| `ibi` | イビルゲッサー |
| `Evil` | EvilGuesser（英語名） |

**検索アルゴリズム:**
1. 入力を正規化（jaconvでカタカナ・ひらがな・ローマ字に変換）
2. 役職名の各表記（カタカナ名・ひらがな変換・ローマ字変換・英語名）に対して部分一致検索
3. 複数ヒット → ボタンリストで選択（最大25件、Discordのボタン上限）
4. 1件ヒット → 即 Embed 表示
5. 0件 → 「`{keyword}` に一致する役職は見つかりませんでした」メッセージ

### 役職詳細 Embed

```
┌────────────────────────────────────┐
│ 🎭 役職名（カタカナ）               │
│ ────────────────────────────────── │
│ [サムネイル: 役職アイコン画像]       │
│ 陣営: クルーメイト                  │
│ カテゴリ: ○○                       │
│ ────────────────────────────────── │
│ 能力説明テキスト（Wiki本文）         │
│ ────────────────────────────────── │
│ 🔗 Wikiで詳細を見る（リンク）        │
└────────────────────────────────────┘
```

- Embedの色：陣営に応じて変化（クルー=青、インポスター=赤、ニュートラル=黄、その他=グレー）
- 画像はWikiページに存在する場合のみ表示

---

## データキャッシュ仕様

### roles_cache.json 構造

```json
{
  "updated_at": "2026-05-06T00:00:00Z",
  "roles": [
    {
      "name": "イビルゲッサー",
      "name_en": "EvilGuesser",
      "faction": "インポスター",
      "category": "キラー",
      "description": "能力説明テキスト...",
      "icon_url": "https://wiki.supernewroles.com/...",
      "wiki_url": "https://wiki.supernewroles.com/ja/Roles/..."
    }
  ]
}
```

### 更新スケジュール
- Bot起動時：キャッシュが存在しない場合のみスクレイピング実行
- 毎日 UTC 0:00（JST 09:00）：自動更新
- Wiki取得失敗時：既存キャッシュを維持し、エラーログ出力

---

## 24時間稼働設計

### Renderデプロイ
- `Procfile` に `web: python bot.py` を記述
- `runtime.txt` に `python-3.11.9` を指定
- 環境変数 `DISCORD_TOKEN` をRenderダッシュボードで設定
- トークン読み込み順序：環境変数 `DISCORD_TOKEN` → `discord token.txt` ファイルの順でフォールバック

### スリープ対策
- `bot.py` 内にFlaskの最小Webサーバー（`/health` エンドポイント）をスレッドで起動
- UptimeRobot（無料）でRenderのURLに15分ごとにpingを送信し、スリープを防止
- Flaskはポート `$PORT`（Renderが自動割り当て）でリッスン

---

## エラーハンドリング

| ケース | 対処 |
|---|---|
| Wiki取得失敗 | 古いキャッシュで継続、コンソールにエラーログ出力 |
| キャッシュファイル未存在（初回起動） | 起動時に即スクレイピング実行 |
| 検索結果0件 | ユーザーへ「見つかりません」メッセージ |
| Discordトークン不正 | 起動時にエラーで終了、ログ出力 |
| ボタンタイムアウト（15分） | discord.pyのView timeout後は操作不可（再コマンド実行を促すメッセージ） |

---

## デプロイ手順（概要）

1. GitHubリポジトリ作成 & コードpush
2. Renderで新規 Web Service 作成、GitHubリポジトリと連携
3. 環境変数 `DISCORD_TOKEN` をRenderで設定
4. Renderが自動ビルド・デプロイ
5. UptimeRobotでRenderの公開URLを登録（15分間隔ping）
6. Discord Developer Portal でスラッシュコマンドを同期

---

## 制約・非機能要件

- トークン節約：Wikiは1日1回のみ取得、コマンドごとの取得は行わない
- Botは ephemeral（本人のみ見える）返答は使用しない（全員が役職情報を見られるように）
- roles_cache.json は `.gitignore` に追加（トークン節約・デプロイ時は再取得）
