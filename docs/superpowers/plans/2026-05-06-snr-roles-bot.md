# SNR 役職検索 Discord Bot 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Super New Roles Wikiから役職データを取得し、ボタンUI・検索コマンドで役職を調べられるDiscord Botを作成する

**Architecture:** 単一ファイル `bot.py` に全機能を実装。Wikiを1日1回スクレイピングして `roles_cache.json` にキャッシュ。Railway上で24時間稼働し、Flask の `/health` エンドポイントを UptimeRobot が ping して起こし続ける。

**Tech Stack:** Python 3.11, discord.py 2.x, beautifulsoup4, requests, jaconv, apscheduler, flask

---

## ファイルマップ

| ファイル | 役割 |
|---|---|
| `bot.py` | Bot全体（スクレイパー・検索・コマンド・UI・スケジューラー・Flaskサーバー） |
| `requirements.txt` | 依存パッケージ |
| `Procfile` | Railway/Render 起動設定 |
| `runtime.txt` | Python バージョン指定 |
| `.gitignore` | roles_cache.json・トークンファイルを除外 |
| `tests/test_search.py` | 検索ロジックの単体テスト |
| `tests/test_scraper.py` | スクレイパーのパーステスト |

---

## Task 1: プロジェクトスキャフォールド

**Files:**
- Create: `requirements.txt`
- Create: `Procfile`
- Create: `runtime.txt`
- Create: `.gitignore`
- Create: `tests/__init__.py`

- [ ] **Step 1: requirements.txt を作成**

```
discord.py==2.3.2
beautifulsoup4==4.12.3
requests==2.32.3
apscheduler==3.10.4
jaconv==0.3.4
flask==3.1.0
pytest==8.3.5
pytest-asyncio==0.24.0
lxml==5.3.0
```

- [ ] **Step 2: Procfile を作成**

```
web: python bot.py
```

- [ ] **Step 3: runtime.txt を作成**

```
python-3.11.9
```

- [ ] **Step 4: .gitignore を作成**

```
roles_cache.json
discord token.txt
.env
__pycache__/
*.pyc
.pytest_cache/
```

- [ ] **Step 5: tests/__init__.py を作成（空ファイル）**

```python
```

- [ ] **Step 6: 依存関係をインストール**

```bash
pip install -r requirements.txt
```

期待出力: `Successfully installed discord.py-2.3.2 ...` （エラーなし）

- [ ] **Step 7: コミット**

```bash
git init
git add requirements.txt Procfile runtime.txt .gitignore tests/__init__.py
git commit -m "chore: initial project scaffold"
```

---

## Task 2: 検索ロジック（TDD）

**Files:**
- Create: `tests/test_search.py`
- Create: `bot.py`（検索関数のみ）

- [ ] **Step 1: テストを書く**

`tests/test_search.py` を作成:

```python
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from bot import normalize_text, search_roles

SAMPLE_ROLES = [
    {"name": "イビルゲッサー", "name_en": "EvilGuesser", "faction": "インポスター", "category": "キラー", "description": "", "icon_url": "", "wiki_url": ""},
    {"name": "シェリフ", "name_en": "Sheriff", "faction": "クルーメイト", "category": "キラー", "description": "", "icon_url": "", "wiki_url": ""},
    {"name": "アーソニスト", "name_en": "Arsonist", "faction": "ニュートラル", "category": "キラー", "description": "", "icon_url": "", "wiki_url": ""},
]

def test_katakana_partial():
    results = search_roles(SAMPLE_ROLES, "イビルゲ")
    assert len(results) == 1
    assert results[0]["name"] == "イビルゲッサー"

def test_hiragana_full():
    results = search_roles(SAMPLE_ROLES, "いびるげっさー")
    assert len(results) == 1
    assert results[0]["name"] == "イビルゲッサー"

def test_hiragana_partial():
    results = search_roles(SAMPLE_ROLES, "いびるげ")
    assert len(results) == 1
    assert results[0]["name"] == "イビルゲッサー"

def test_romaji_partial():
    results = search_roles(SAMPLE_ROLES, "ibiruge")
    assert len(results) == 1
    assert results[0]["name"] == "イビルゲッサー"

def test_romaji_short():
    results = search_roles(SAMPLE_ROLES, "ibi")
    assert len(results) == 1
    assert results[0]["name"] == "イビルゲッサー"

def test_english_partial():
    results = search_roles(SAMPLE_ROLES, "Evil")
    assert len(results) == 1
    assert results[0]["name"] == "イビルゲッサー"

def test_english_lowercase():
    results = search_roles(SAMPLE_ROLES, "evil")
    assert len(results) == 1
    assert results[0]["name"] == "イビルゲッサー"

def test_no_match():
    results = search_roles(SAMPLE_ROLES, "zzzzz")
    assert len(results) == 0

def test_multiple_match():
    # "r" はローマ字変換後 "る" → シェリフもアーソニストもヒットしないが、
    # 英語名に "r" を含む EvilGuesser, Sheriff, Arsonist はすべてヒット
    results = search_roles(SAMPLE_ROLES, "r")
    names = [r["name"] for r in results]
    assert "シェリフ" in names
    assert "アーソニスト" in names
```

- [ ] **Step 2: テストが失敗することを確認**

```bash
pytest tests/test_search.py -v
```

期待出力: `ERROR ... ModuleNotFoundError: No module named 'bot'`（まだ実装していないのでエラー）

- [ ] **Step 3: bot.py に検索ロジックを実装**

`bot.py` を作成:

```python
import os
import json
import threading
import logging
from datetime import datetime

import jaconv
import requests
from bs4 import BeautifulSoup
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from flask import Flask
import discord
from discord import app_commands
from discord.ext import commands

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CACHE_FILE = "roles_cache.json"
WIKI_LIST_URL = "https://wiki.supernewroles.com/ja/Roles/役職一覧"

FACTION_COLORS = {
    "クルーメイト": discord.Color.blue(),
    "インポスター": discord.Color.red(),
    "ニュートラル": discord.Color.gold(),
}


def normalize_text(text: str) -> str:
    """任意の文字列をカタカナに正規化する（ローマ字・ひらがな対応）"""
    text = text.lower()
    text = jaconv.alphabet2kana(text)   # ローマ字 → ひらがな
    text = jaconv.h2k(text)             # ひらがな → カタカナ
    return text


def search_roles(roles: list[dict], keyword: str) -> list[dict]:
    """カタカナ・ひらがな・ローマ字・英語名の部分一致で役職を検索する"""
    kw_kata = normalize_text(keyword)
    kw_lower = keyword.lower()
    results = []
    for role in roles:
        name_kata = normalize_text(role["name"])
        name_en_lower = role.get("name_en", "").lower()
        if kw_kata in name_kata or kw_lower in name_en_lower:
            results.append(role)
    return results
```

- [ ] **Step 4: テストがすべて通ることを確認**

```bash
pytest tests/test_search.py -v
```

期待出力:
```
test_search.py::test_katakana_partial PASSED
test_search.py::test_hiragana_full PASSED
test_search.py::test_hiragana_partial PASSED
test_search.py::test_romaji_partial PASSED
test_search.py::test_romaji_short PASSED
test_search.py::test_english_partial PASSED
test_search.py::test_english_lowercase PASSED
test_search.py::test_no_match PASSED
test_search.py::test_multiple_match PASSED
9 passed
```

- [ ] **Step 5: コミット**

```bash
git add bot.py tests/test_search.py
git commit -m "feat: add search logic with jaconv normalization"
```

---

## Task 3: Wikiスクレイパー（TDD）

**Files:**
- Create: `tests/test_scraper.py`
- Modify: `bot.py`（スクレイパー関数を追加）

**注意:** このタスクの最初にWikiのHTML構造を実際に確認し、パーサーをその構造に合わせる。

- [ ] **Step 1: WikiのHTML構造を確認する**

```bash
python -c "
import requests
from bs4 import BeautifulSoup
r = requests.get('https://wiki.supernewroles.com/ja/Roles/役職一覧', headers={'User-Agent': 'Mozilla/5.0'})
soup = BeautifulSoup(r.text, 'lxml')
# 最初の役職リンクを探す
links = soup.find_all('a', href=True)
for l in links[:30]:
    if '/ja/Roles/' in l.get('href', '') and l.get_text(strip=True):
        print(l['href'], '|', l.get_text(strip=True))
"
```

出力を確認し、役職ページのURLパターンと役職名の取得方法を把握する。

- [ ] **Step 2: 役職一覧ページの構造を確認する（陣営テーブル）**

```bash
python -c "
import requests
from bs4 import BeautifulSoup
r = requests.get('https://wiki.supernewroles.com/ja/Roles/役職一覧', headers={'User-Agent': 'Mozilla/5.0'})
soup = BeautifulSoup(r.text, 'lxml')
# テーブルやセクションの構造を確認
tables = soup.find_all('table')
print(f'テーブル数: {len(tables)}')
if tables:
    print(tables[0].prettify()[:2000])
# h2/h3 見出しを確認
for h in soup.find_all(['h2','h3']):
    print('見出し:', h.get_text(strip=True))
"
```

出力を確認し、陣営ごとの区切り方を把握する。

- [ ] **Step 3: 役職個別ページの構造を確認する**

Step 1 で取得した役職URLのひとつを使って個別ページを確認:

```bash
python -c "
import requests
from bs4 import BeautifulSoup
# Step 1 で得た役職URLの1つを使う（例: https://wiki.supernewroles.com/ja/Roles/EvilGuesser）
r = requests.get('https://wiki.supernewroles.com/ja/Roles/EvilGuesser', headers={'User-Agent': 'Mozilla/5.0'})
soup = BeautifulSoup(r.text, 'lxml')
# アイコン画像を探す
imgs = soup.find_all('img')
for img in imgs[:5]:
    print('img src:', img.get('src',''))
# 説明文を探す
content = soup.find('div', class_='mw-parser-output') or soup.find('div', id='mw-content-text')
if content:
    print(content.get_text()[:500])
"
```

- [ ] **Step 4: スクレイパー関数のテストを書く（実際のHTML構造を基に）**

Step 1〜3 で確認した構造を基に `tests/test_scraper.py` を作成する。以下はテンプレートで、実際のHTMLに合わせて `SAMPLE_LIST_HTML` と `SAMPLE_ROLE_HTML` を変更すること:

```python
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from unittest.mock import patch, MagicMock
from bot import parse_role_list, parse_role_detail

# Step 1〜3 で確認した実際のHTMLの一部を貼る
SAMPLE_LIST_HTML = """
<html><body>
<h2>インポスター</h2>
<ul>
  <li><a href="/ja/Roles/EvilGuesser">イビルゲッサー</a></li>
</ul>
<h2>クルーメイト</h2>
<ul>
  <li><a href="/ja/Roles/Sheriff">シェリフ</a></li>
</ul>
</body></html>
"""

SAMPLE_ROLE_HTML = """
<html><body>
<div class="mw-parser-output">
  <img src="https://wiki.supernewroles.com/images/icon.png" />
  <p>能力説明テキストです。</p>
</div>
</body></html>
"""

def test_parse_role_list_returns_roles():
    roles = parse_role_list(SAMPLE_LIST_HTML)
    assert len(roles) >= 1

def test_parse_role_list_faction():
    roles = parse_role_list(SAMPLE_LIST_HTML)
    evilguesser = next((r for r in roles if "EvilGuesser" in r["wiki_url"]), None)
    assert evilguesser is not None
    assert evilguesser["faction"] == "インポスター"

def test_parse_role_detail_description():
    desc, icon_url = parse_role_detail(SAMPLE_ROLE_HTML)
    assert "能力説明" in desc

def test_parse_role_detail_icon():
    desc, icon_url = parse_role_detail(SAMPLE_ROLE_HTML)
    assert icon_url == "https://wiki.supernewroles.com/images/icon.png"
```

**重要:** `SAMPLE_LIST_HTML` と `SAMPLE_ROLE_HTML` は Step 1〜3 の実際の出力に合わせて書き換えること。

- [ ] **Step 5: テストが失敗することを確認**

```bash
pytest tests/test_scraper.py -v
```

期待出力: `ImportError: cannot import name 'parse_role_list' from 'bot'`

- [ ] **Step 6: スクレイパー関数を bot.py に実装する**

`bot.py` の `search_roles` 関数の後に以下を追加（実際のHTML構造に合わせて調整すること）:

```python
WIKI_BASE_URL = "https://wiki.supernewroles.com"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; SNR-Bot/1.0)"}

# 陣営名のマッピング（WikiのHTMLで使われる文字列 → 統一表記）
FACTION_MAP = {
    "インポスター": "インポスター",
    "クルーメイト": "クルーメイト",
    "ニュートラル": "ニュートラル",
    "Impostor": "インポスター",
    "Crewmate": "クルーメイト",
    "Neutral": "ニュートラル",
}


def parse_role_list(html: str) -> list[dict]:
    """役職一覧ページのHTMLから役職リスト（名前・陣営・URL）を抽出する"""
    soup = BeautifulSoup(html, "lxml")
    roles = []
    current_faction = "その他"

    # h2/h3タグで陣営を判定し、直後のリンクを役職として取得
    # 実際のHTML構造に合わせてこのロジックを調整すること
    for tag in soup.find_all(["h2", "h3", "a"]):
        if tag.name in ("h2", "h3"):
            text = tag.get_text(strip=True)
            current_faction = FACTION_MAP.get(text, text if text else "その他")
        elif tag.name == "a":
            href = tag.get("href", "")
            name = tag.get_text(strip=True)
            if "/ja/Roles/" in href and name and name != "役職一覧":
                wiki_url = WIKI_BASE_URL + href if href.startswith("/") else href
                roles.append({
                    "name": name,
                    "name_en": href.split("/")[-1],
                    "faction": current_faction,
                    "category": "",
                    "description": "",
                    "icon_url": "",
                    "wiki_url": wiki_url,
                })
    return roles


def parse_role_detail(html: str) -> tuple[str, str]:
    """役職個別ページのHTMLから説明文とアイコンURLを抽出する"""
    soup = BeautifulSoup(html, "lxml")

    # アイコン画像（最初に見つかるwikiの画像）
    icon_url = ""
    for img in soup.find_all("img"):
        src = img.get("src", "")
        if src and "Special:" not in src and src.startswith("http"):
            icon_url = src
            break

    # 説明文（メインコンテンツ領域のテキスト）
    content = (
        soup.find("div", class_="mw-parser-output")
        or soup.find("div", id="mw-content-text")
    )
    description = content.get_text(separator="\n", strip=True)[:1000] if content else ""

    return description, icon_url


def fetch_roles() -> list[dict]:
    """WikiからすべてのSNR役職を取得してリストで返す"""
    logger.info("Wikiから役職データを取得中...")
    try:
        resp = requests.get(WIKI_LIST_URL, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        roles = parse_role_list(resp.text)
    except Exception as e:
        logger.error(f"役職一覧ページの取得失敗: {e}")
        return []

    for role in roles:
        try:
            r = requests.get(role["wiki_url"], headers=HEADERS, timeout=15)
            r.raise_for_status()
            description, icon_url = parse_role_detail(r.text)
            role["description"] = description
            role["icon_url"] = icon_url
        except Exception as e:
            logger.warning(f"{role['name']} の詳細取得失敗: {e}")

    logger.info(f"取得完了: {len(roles)}役職")
    return roles
```

- [ ] **Step 7: テストをパスさせる（テストのHTMLに合わせてパーサーを調整）**

```bash
pytest tests/test_scraper.py -v
```

テストが失敗する場合、`parse_role_list` と `parse_role_detail` の実装を Step 1〜3 で確認した実際のHTML構造に合わせて調整する。

期待出力: `4 passed`

- [ ] **Step 8: 全テストを実行して既存テストが壊れていないことを確認**

```bash
pytest tests/ -v
```

期待出力: `13 passed`

- [ ] **Step 9: コミット**

```bash
git add bot.py tests/test_scraper.py
git commit -m "feat: add wiki scraper with faction parsing"
```

---

## Task 4: キャッシュ管理・トークン読み込み

**Files:**
- Modify: `bot.py`（cache関数・token関数を追加）

- [ ] **Step 1: bot.py にキャッシュ関数とトークン読み込みを追加**

`parse_role_list` 関数の前（importの後）に以下を追加:

```python
def load_token() -> str:
    """環境変数 → discord token.txt の順でトークンを読み込む"""
    token = os.environ.get("DISCORD_TOKEN")
    if token:
        return token
    try:
        with open("discord token.txt", "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        raise RuntimeError("DISCORD_TOKEN 環境変数か 'discord token.txt' が必要です")


def load_cache() -> list[dict]:
    """roles_cache.json からキャッシュを読み込む。ファイルなしは空リストを返す"""
    if not os.path.exists(CACHE_FILE):
        return []
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("roles", [])
    except (json.JSONDecodeError, KeyError):
        return []


def save_cache(roles: list[dict]) -> None:
    """役職リストを roles_cache.json に保存する"""
    data = {
        "updated_at": datetime.utcnow().isoformat() + "Z",
        "roles": roles,
    }
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info(f"キャッシュ保存完了: {len(roles)}役職")
```

- [ ] **Step 2: キャッシュの動作確認（手動）**

```bash
python -c "
from bot import save_cache, load_cache
test_roles = [{'name': 'テスト', 'name_en': 'Test', 'faction': 'クルーメイト', 'category': '', 'description': 'テスト説明', 'icon_url': '', 'wiki_url': 'https://example.com'}]
save_cache(test_roles)
loaded = load_cache()
assert loaded[0]['name'] == 'テスト', '読み込み失敗'
print('キャッシュ保存・読み込み OK')
import os; os.remove('roles_cache.json')
"
```

期待出力: `キャッシュ保存・読み込み OK`

- [ ] **Step 3: コミット**

```bash
git add bot.py
git commit -m "feat: add cache management and token loading"
```

---

## Task 5: Flaskヘルスサーバー + Discordクライアント基盤

**Files:**
- Modify: `bot.py`（Flask・Discordクライアント・on_readyを追加）

- [ ] **Step 1: bot.py の末尾にFlaskとDiscordクライアントを追加**

`fetch_roles` 関数の後に以下をすべて追加:

```python
# --- Flask ヘルスサーバー（UptimeRobot用） ---
flask_app = Flask(__name__)


@flask_app.route("/health")
def health():
    return "OK", 200


def run_flask() -> None:
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host="0.0.0.0", port=port, use_reloader=False)


# --- Discord Bot ---
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)


async def refresh_cache() -> None:
    """スケジューラーから呼ばれるキャッシュ更新"""
    roles = fetch_roles()
    if roles:
        save_cache(roles)
        logger.info("キャッシュ自動更新完了")
    else:
        logger.warning("キャッシュ更新失敗: 既存キャッシュを維持")


@bot.event
async def on_ready():
    logger.info(f"Botログイン: {bot.user}")

    # 初回起動時のキャッシュ取得
    if not load_cache():
        logger.info("キャッシュなし: スクレイピング実行中...")
        roles = fetch_roles()
        if roles:
            save_cache(roles)

    # 毎日UTC 0:00 に自動更新
    scheduler = AsyncIOScheduler()
    scheduler.add_job(refresh_cache, "cron", hour=0, minute=0)
    scheduler.start()

    # スラッシュコマンドをDiscordに登録
    await bot.tree.sync()
    logger.info("スラッシュコマンド同期完了")

    # Flaskサーバーをバックグラウンドで起動
    threading.Thread(target=run_flask, daemon=True).start()
    logger.info("Flaskヘルスサーバー起動")
```

- [ ] **Step 2: bot.py の末尾（ファイルの最後）にエントリポイントを追加**

```python
if __name__ == "__main__":
    bot.run(load_token())
```

- [ ] **Step 3: 構文エラーがないことを確認**

```bash
python -c "import bot; print('構文OK')"
```

期待出力: `構文OK`（DiscordのImportエラーが出る場合は `pip install discord.py` を再実行）

- [ ] **Step 4: コミット**

```bash
git add bot.py
git commit -m "feat: add Flask health server and Discord client foundation"
```

---

## Task 6: 役職詳細Embed ビルダー

**Files:**
- Modify: `bot.py`（build_role_embed 関数を追加）

- [ ] **Step 1: bot.py の on_ready の前に Embed ビルダーを追加**

```python
def build_role_embed(role: dict) -> discord.Embed:
    """役職情報から discord.Embed を生成する"""
    faction = role.get("faction", "その他")
    color = FACTION_COLORS.get(faction, discord.Color.greyple())

    embed = discord.Embed(
        title=f"🎭 {role['name']}",
        url=role.get("wiki_url") or None,
        color=color,
    )

    embed.add_field(name="陣営", value=faction, inline=True)
    if role.get("category"):
        embed.add_field(name="カテゴリ", value=role["category"], inline=True)

    if role.get("description"):
        # Discord の field value は 1024文字制限
        desc = role["description"][:1000]
        embed.add_field(name="能力説明", value=desc, inline=False)

    if role.get("icon_url"):
        embed.set_thumbnail(url=role["icon_url"])

    if role.get("wiki_url"):
        embed.set_footer(text="🔗 Wikiで詳細を見る → " + role["wiki_url"])

    return embed
```

- [ ] **Step 2: Embed の動作を簡易確認**

```bash
python -c "
from bot import build_role_embed
import discord
test_role = {
    'name': 'イビルゲッサー', 'name_en': 'EvilGuesser', 'faction': 'インポスター',
    'category': 'キラー', 'description': '能力説明テスト', 'icon_url': '', 'wiki_url': 'https://example.com'
}
embed = build_role_embed(test_role)
assert embed.title == '🎭 イビルゲッサー'
assert embed.color == discord.Color.red()
print('Embed OK')
"
```

期待出力: `Embed OK`

- [ ] **Step 3: コミット**

```bash
git add bot.py
git commit -m "feat: add role embed builder with faction colors"
```

---

## Task 7: `/roles` コマンド（陣営ボタン → ページネーション → 役職詳細）

**Files:**
- Modify: `bot.py`（View クラスと `/roles` コマンドを追加）

- [ ] **Step 1: bot.py の build_role_embed の前に View クラスを追加**

```python
ROLES_PER_PAGE = 10


class RoleDetailView(discord.ui.View):
    """役職詳細表示後の「戻る」ボタン"""

    def __init__(self, back_view: discord.ui.View):
        super().__init__(timeout=600)
        self.back_view = back_view

    @discord.ui.button(label="◀ 一覧に戻る", style=discord.ButtonStyle.secondary)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            content="役職を選んでください:",
            embed=None,
            view=self.back_view,
        )


class RoleListView(discord.ui.View):
    """役職一覧ページネーション + 役職選択ボタン"""

    def __init__(self, roles: list[dict], faction: str, page: int = 0):
        super().__init__(timeout=600)
        self.roles = roles
        self.faction = faction
        self.page = page
        self.total_pages = max(1, (len(roles) + ROLES_PER_PAGE - 1) // ROLES_PER_PAGE)
        self._build_buttons()

    def _build_buttons(self):
        self.clear_items()
        start = self.page * ROLES_PER_PAGE
        page_roles = self.roles[start: start + ROLES_PER_PAGE]

        for role in page_roles:
            btn = discord.ui.Button(
                label=role["name"][:80],
                style=discord.ButtonStyle.primary,
                custom_id=f"role_{role['name']}",
            )
            btn.callback = self._make_role_callback(role)
            self.add_item(btn)

        if self.total_pages > 1:
            prev_btn = discord.ui.Button(
                label="◀ 前へ",
                style=discord.ButtonStyle.secondary,
                disabled=(self.page == 0),
            )
            next_btn = discord.ui.Button(
                label="次へ ▶",
                style=discord.ButtonStyle.secondary,
                disabled=(self.page >= self.total_pages - 1),
            )
            prev_btn.callback = self._prev_page
            next_btn.callback = self._next_page
            self.add_item(prev_btn)
            self.add_item(next_btn)

    def _make_role_callback(self, role: dict):
        async def callback(interaction: discord.Interaction):
            embed = build_role_embed(role)
            await interaction.response.edit_message(
                content=None,
                embed=embed,
                view=RoleDetailView(back_view=self),
            )
        return callback

    async def _prev_page(self, interaction: discord.Interaction):
        self.page -= 1
        self._build_buttons()
        await interaction.response.edit_message(
            content=f"**{self.faction}** の役職一覧（{self.page + 1}/{self.total_pages}ページ）:",
            view=self,
        )

    async def _next_page(self, interaction: discord.Interaction):
        self.page += 1
        self._build_buttons()
        await interaction.response.edit_message(
            content=f"**{self.faction}** の役職一覧（{self.page + 1}/{self.total_pages}ページ）:",
            view=self,
        )


class FactionView(discord.ui.View):
    """陣営選択ボタン"""

    FACTIONS = ["クルーメイト", "インポスター", "ニュートラル", "その他"]

    def __init__(self):
        super().__init__(timeout=600)
        for faction in self.FACTIONS:
            btn = discord.ui.Button(
                label=faction,
                style=discord.ButtonStyle.primary,
                custom_id=f"faction_{faction}",
            )
            btn.callback = self._make_faction_callback(faction)
            self.add_item(btn)

    def _make_faction_callback(self, faction: str):
        async def callback(interaction: discord.Interaction):
            all_roles = load_cache()
            if faction == "その他":
                roles = [r for r in all_roles if r.get("faction") not in ("クルーメイト", "インポスター", "ニュートラル")]
            else:
                roles = [r for r in all_roles if r.get("faction") == faction]

            if not roles:
                await interaction.response.send_message(
                    f"**{faction}** の役職データがありません。", ephemeral=True
                )
                return

            view = RoleListView(roles, faction)
            total_pages = view.total_pages
            await interaction.response.edit_message(
                content=f"**{faction}** の役職一覧（1/{total_pages}ページ）:",
                view=view,
            )
        return callback
```

- [ ] **Step 2: on_ready の前に `/roles` コマンドを追加**

```python
@bot.tree.command(name="roles", description="SNRの役職一覧を陣営別に表示します")
async def roles_command(interaction: discord.Interaction):
    roles = load_cache()
    if not roles:
        await interaction.response.send_message(
            "役職データを読み込み中です。しばらくしてからもう一度お試しください。",
            ephemeral=True,
        )
        return
    await interaction.response.send_message(
        "陣営を選んでください:", view=FactionView()
    )
```

- [ ] **Step 3: 構文エラーがないことを確認**

```bash
python -c "import bot; print('構文OK')"
```

- [ ] **Step 4: コミット**

```bash
git add bot.py
git commit -m "feat: add /roles command with faction buttons and pagination"
```

---

## Task 8: `/search` コマンド

**Files:**
- Modify: `bot.py`（SearchResultView と `/search` コマンドを追加）

- [ ] **Step 1: bot.py の roles_command の後に `/search` コマンドを追加**

```python
class SearchResultView(discord.ui.View):
    """検索結果が複数のときに役職を選択するボタンリスト"""

    def __init__(self, results: list[dict]):
        super().__init__(timeout=600)
        for role in results[:25]:  # Discord の上限は25ボタン
            btn = discord.ui.Button(
                label=role["name"][:80],
                style=discord.ButtonStyle.primary,
            )
            btn.callback = self._make_callback(role)
            self.add_item(btn)

    def _make_callback(self, role: dict):
        async def callback(interaction: discord.Interaction):
            embed = build_role_embed(role)
            await interaction.response.edit_message(
                content=None, embed=embed, view=None
            )
        return callback


@bot.tree.command(name="search", description="役職を名前で検索します（部分一致・ひらがな・ローマ字対応）")
@app_commands.describe(keyword="検索キーワード（例: イビルゲ、いびるげ、ibiruge）")
async def search_command(interaction: discord.Interaction, keyword: str):
    roles = load_cache()
    if not roles:
        await interaction.response.send_message(
            "役職データを読み込み中です。しばらくしてからもう一度お試しください。",
            ephemeral=True,
        )
        return

    results = search_roles(roles, keyword)

    if not results:
        await interaction.response.send_message(
            f"**「{keyword}」** に一致する役職は見つかりませんでした。\n"
            "カタカナ・ひらがな・ローマ字で試してみてください。"
        )
        return

    if len(results) == 1:
        embed = build_role_embed(results[0])
        await interaction.response.send_message(embed=embed)
        return

    await interaction.response.send_message(
        f"**「{keyword}」** の検索結果: {len(results)} 件（最大25件表示）\n役職を選んでください:",
        view=SearchResultView(results),
    )
```

- [ ] **Step 2: 構文エラーがないことを確認**

```bash
python -c "import bot; print('構文OK')"
```

- [ ] **Step 3: コミット**

```bash
git add bot.py
git commit -m "feat: add /search command with multi-result selection"
```

---

## Task 9: ローカル動作テスト

**Files:** なし（動作確認のみ）

- [ ] **Step 1: Botをローカルで起動する**

```bash
python bot.py
```

期待ログ出力:
```
INFO:bot:Wikiから役職データを取得中...
INFO:bot:取得完了: XX役職
INFO:bot:キャッシュ保存完了: XX役職
INFO:bot:Botログイン: BotName#XXXX
INFO:bot:スラッシュコマンド同期完了
INFO:bot:Flaskヘルスサーバー起動
```

- [ ] **Step 2: Discordで `/roles` を実行**

1. Botが参加しているサーバーで `/roles` を入力
2. 陣営ボタン（クルーメイト・インポスター・ニュートラル・その他）が表示されることを確認
3. 陣営ボタンを押して役職一覧が表示されることを確認
4. ページネーション（前へ/次へ）の動作を確認
5. 役職名ボタンを押してEmbedが表示されることを確認
6. 「◀ 一覧に戻る」で役職一覧に戻ることを確認

- [ ] **Step 3: Discordで `/search` を実行**

以下のキーワードでテスト:
- `/search keyword:イビルゲ` → 1件ヒット→Embed表示
- `/search keyword:いびるげ` → 同上
- `/search keyword:ibi` → 同上
- `/search keyword:Evil` → 同上
- `/search keyword:あ` → 複数件→ボタンリスト表示
- `/search keyword:zzzzz` → 0件→「見つかりませんでした」

- [ ] **Step 4: ヘルスエンドポイントを確認**

```bash
curl http://localhost:8080/health
```

期待出力: `OK`

- [ ] **Step 5: Botを停止して全テストを実行**

Ctrl+C で停止後:

```bash
pytest tests/ -v
```

期待出力: `13 passed`

- [ ] **Step 6: コミット**

```bash
git add .
git commit -m "test: verify local integration tests pass"
```

---

## Task 10: Railway へデプロイ

**Files:** なし（Railway の設定作業）

- [ ] **Step 1: GitHubリポジトリを作成してpush**

```bash
# GitHubで新規リポジトリ (例: snr-roles-bot) を作成後:
git remote add origin https://github.com/<username>/snr-roles-bot.git
git branch -M main
git push -u origin main
```

- [ ] **Step 2: Railway にサインアップ・プロジェクト作成**

1. https://railway.app にアクセス（GitHubアカウントでサインイン）
2. 「New Project」→「Deploy from GitHub repo」
3. `snr-roles-bot` リポジトリを選択
4. Railway が自動的に `Procfile` を検出してビルド開始

- [ ] **Step 3: 環境変数を設定**

Railway のダッシュボードで:
1. プロジェクトを開く → 「Variables」タブ
2. 「Add Variable」→ `DISCORD_TOKEN` = `discord token.txt` の中身のトークン値

- [ ] **Step 4: デプロイログを確認**

Railway の「Deployments」タブでログを確認:
```
INFO:bot:Wikiから役職データを取得中...
INFO:bot:取得完了: XX役職
INFO:bot:Botログイン: BotName#XXXX
INFO:bot:スラッシュコマンド同期完了
```

- [ ] **Step 5: デプロイURLを確認**

Railway ダッシュボードの「Settings」→「Networking」→「Generate Domain」でURLを取得（例: `https://snr-roles-bot.up.railway.app`）

- [ ] **Step 6: UptimeRobot でスリープ防止を設定**

1. https://uptimerobot.com に登録（無料）
2. 「Add New Monitor」
3. Monitor Type: `HTTP(s)`
4. URL: `https://snr-roles-bot.up.railway.app/health`
5. Monitoring Interval: `15 minutes`
6. 「Create Monitor」

- [ ] **Step 7: 本番環境でDiscordコマンドを動作確認**

Task 9 Step 2・3と同じテストを本番Botで実行し、正常動作を確認する。

---

## チェックリスト（スペックカバレッジ確認）

| 要件 | 対応タスク |
|---|---|
| Wikiから全役職取得 | Task 3 |
| 役職一覧をボタンで表示 | Task 7 |
| 陣営別タブ | Task 7 (FactionView) |
| ページネーション | Task 7 (RoleListView) |
| 役職詳細（能力・陣営・アイコン）Embed | Task 6 |
| 陣営別Embed色分け | Task 6 (FACTION_COLORS) |
| `/search` スラッシュコマンド | Task 8 |
| カタカナ部分一致 | Task 2 |
| ひらがな部分一致 | Task 2 |
| ローマ字部分一致 | Task 2 |
| 英語名部分一致 | Task 2 |
| 複数ヒット→ボタン選択 | Task 8 |
| 1件ヒット→即Embed | Task 8 |
| 0件→メッセージ | Task 8 |
| 1日1回自動更新 | Task 5 (APScheduler) |
| 24時間稼働（Railway） | Task 10 |
| UptimeRobot スリープ防止 | Task 10 |
| トークン環境変数/txtフォールバック | Task 4 |
