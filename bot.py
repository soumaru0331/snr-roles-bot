import os
import re
import json
import threading
import logging
from datetime import datetime

import jaconv
import pykakasi
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


_LOANWORD_MAP = [
    # jaconvが標準ローマ字で変換してしまう英語由来の音を先に変換
    ("di", "でぃ"), ("ti", "てぃ"), ("du", "どぅ"), ("tu", "とぅ"),
    ("fa", "ふぁ"), ("fi", "ふぃ"), ("fe", "ふぇ"), ("fo", "ふぉ"),
    ("va", "ゔぁ"), ("vi", "ゔぃ"), ("vu", "ゔ"),  ("ve", "ゔぇ"), ("vo", "ゔぉ"),
    ("wi", "うぃ"), ("we", "うぇ"), ("wo", "うぉ"),
]

_kakasi = pykakasi.kakasi()


def _kanji_to_hira(text: str) -> str:
    """漢字を含むテキストをひらがなに変換する（ASCII・カナはそのまま保持）"""
    result = _kakasi.convert(text)
    return ''.join(item.get('hira') or item.get('orig', '') for item in result)


def normalize_text(text: str) -> str:
    """任意の文字列をカタカナに正規化する（漢字・ローマ字・ひらがな対応）"""
    text = _kanji_to_hira(text)          # 漢字 → ひらがな（ASCII・カナは保持）
    text = text.lower()
    # 母音後の 'ny' → 'んy'（例: inyo→いんよ、kinyou→きんよう）
    text = re.sub(r'(?<=[aiueo])ny', 'んy', text)
    for rom, kana in _LOANWORD_MAP:
        text = text.replace(rom, kana)
    text = jaconv.alphabet2kana(text)   # 残りのローマ字 → ひらがな
    text = jaconv.hira2kata(text)       # ひらがな → カタカナ
    return text


_SMALL_TO_LARGE = str.maketrans("ァィゥェォャュョヮ", "アイウエオヤユヨワ")


def _strip_noise(text: str) -> str:
    """ローマ字変換ノイズ（ッ・ー・小書きカナ）を除去して曖昧マッチを可能にする"""
    text = text.replace("ッ", "").replace("ー", "")
    text = text.translate(_SMALL_TO_LARGE)  # シェ→シエ、ウォ→ウオ 等
    return text


_TRAILING_CONSONANTS_RE = re.compile(r'[bcdfghjklmnpqrstvwxyz]+$')


def _normalize_partial(keyword: str) -> str:
    """末尾の子音クラスタを除去してから正規化（'dim'→'di'→'ディ' 等の部分入力対応）"""
    text = _kanji_to_hira(keyword)
    text = text.lower()
    text = re.sub(r'(?<=[aiueo])ny', 'んy', text)
    for rom, kana in _LOANWORD_MAP:
        text = text.replace(rom, kana)
    text = _TRAILING_CONSONANTS_RE.sub('', text)
    if not text:
        return ''
    text = jaconv.alphabet2kana(text)
    text = jaconv.hira2kata(text)
    return text


def search_roles(roles: list, keyword: str) -> list:
    """カタカナ・ひらがな・ローマ字の部分一致で役職を検索する"""
    kw_kata = normalize_text(keyword)
    kw_clean = _strip_noise(kw_kata)
    kw_partial = _strip_noise(_normalize_partial(keyword))
    results = []
    for role in roles:
        name_kata = normalize_text(role["name"])
        name_clean = _strip_noise(name_kata)
        if (kw_clean and kw_clean in name_clean) or \
                (kw_partial and kw_partial != kw_clean and kw_partial in name_clean):
            results.append(role)
    return results


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


def load_cache() -> list:
    """roles_cache.json からキャッシュを読み込む。ファイルなしは空リストを返す"""
    if not os.path.exists(CACHE_FILE):
        return []
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("roles", [])
    except (json.JSONDecodeError, KeyError):
        return []


def save_cache(roles: list) -> None:
    """役職リストを roles_cache.json に保存する"""
    data = {
        "updated_at": datetime.utcnow().isoformat() + "Z",
        "roles": roles,
    }
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info(f"キャッシュ保存完了: {len(roles)}役職")


WIKI_BASE_URL = "https://wiki.supernewroles.com"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; SNR-Bot/1.0)"}

FACTION_MAP = {
    "Impostor": "インポスター",
    "Crewmate": "クルーメイト",
    "Neutral": "ニュートラル",
    "Ghost": "幽霊",
    "Modifier": "モディファイア",
}


def parse_role_list(html: str) -> list:
    """役職一覧ページのHTMLから役職リストを抽出する"""
    soup = BeautifulSoup(html, "html.parser")
    roles = []
    seen = set()

    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        name = a.get_text(strip=True)

        if not href.endswith(".md") or not name:
            continue

        parts = href[:-3].split("/")  # .md を除去してスラッシュで分割
        if len(parts) < 2:
            continue

        faction_prefix = parts[0]
        clean_path = href[:-3]  # .md を除去
        wiki_url = WIKI_BASE_URL + "/ja/Roles/" + clean_path

        if wiki_url in seen:
            continue
        seen.add(wiki_url)

        roles.append({
            "name": name,
            "name_en": "",
            "faction": FACTION_MAP.get(faction_prefix, "その他"),
            "category": faction_prefix,
            "description": "",
            "icon_url": "",
            "wiki_url": wiki_url,
        })

    return roles


def parse_role_detail(html: str) -> tuple:
    """役職個別ページのHTMLから説明文とアイコンURLを抽出する"""
    soup = BeautifulSoup(html, "html.parser")

    icon_url = ""
    for img in soup.find_all("img"):
        src = img.get("src", "")
        if src and src.startswith("http") and "icon" in src.lower():
            icon_url = src
            break

    container = soup.find("div", class_="container")
    description = ""

    if container:
        full_text = container.get_text(separator="\n", strip=True)
        if "役職説明" in full_text:
            after_desc = full_text.split("役職説明", 1)[1]
            if "ゲーム設定" in after_desc:
                description = after_desc.split("ゲーム設定", 1)[0].strip()
            else:
                description = after_desc[:800].strip()
        else:
            description = full_text[:800]

    return description[:1000], icon_url


def fetch_roles() -> list:
    """WikiからすべてのSNR役職を取得してリストで返す"""
    logger.info("Wikiから役職データを取得中...")
    try:
        resp = requests.get(WIKI_LIST_URL, headers=HEADERS, timeout=30)
        resp.encoding = "utf-8"
        resp.raise_for_status()
        roles = parse_role_list(resp.text)
    except Exception as e:
        logger.error(f"役職一覧ページの取得失敗: {e}")
        return []

    for role in roles:
        try:
            r = requests.get(role["wiki_url"], headers=HEADERS, timeout=15)
            r.encoding = "utf-8"
            r.raise_for_status()
            description, icon_url = parse_role_detail(r.text)
            role["description"] = description
            role["icon_url"] = icon_url
        except Exception as e:
            logger.warning(f"{role['name']} の詳細取得失敗: {e}")

    logger.info(f"取得完了: {len(roles)}役職")
    return roles


# --- Flask ヘルスサーバー（UptimeRobot用） ---
flask_app = Flask(__name__)


@flask_app.route("/health")
def health():
    return "OK", 200


def run_flask() -> None:
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host="0.0.0.0", port=port, use_reloader=False)


# --- Discord Bot ---
ROLES_PER_PAGE = 10
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)


# --- Embed ビルダー ---
def build_role_embed(role: dict) -> discord.Embed:
    faction = role.get("faction", "その他")
    color = FACTION_COLORS.get(faction, discord.Color.greyple())

    embed = discord.Embed(
        title=f"🎭 {role['name']}",
        url=role.get("wiki_url") or None,
        color=color,
    )
    embed.add_field(name="陣営", value=faction, inline=True)

    if role.get("description"):
        desc = role["description"][:1000]
        embed.add_field(name="役職説明", value=desc, inline=False)

    if role.get("icon_url"):
        embed.set_thumbnail(url=role["icon_url"])

    if role.get("wiki_url"):
        embed.set_footer(text="🔗 Wikiで詳細を見る → " + role["wiki_url"])

    return embed


# --- UI Views ---
class RoleDetailView(discord.ui.View):
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
    def __init__(self, roles: list, faction: str, page: int = 0):
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
    FACTIONS = ["クルーメイト", "インポスター", "ニュートラル", "幽霊", "モディファイア", "その他"]

    def __init__(self):
        super().__init__(timeout=600)
        for faction in self.FACTIONS:
            btn = discord.ui.Button(
                label=faction,
                style=discord.ButtonStyle.primary,
            )
            btn.callback = self._make_faction_callback(faction)
            self.add_item(btn)

    def _make_faction_callback(self, faction: str):
        async def callback(interaction: discord.Interaction):
            all_roles = load_cache()
            known = {"クルーメイト", "インポスター", "ニュートラル", "幽霊", "モディファイア"}
            if faction == "その他":
                roles = [r for r in all_roles if r.get("faction") not in known]
            else:
                roles = [r for r in all_roles if r.get("faction") == faction]

            if not roles:
                await interaction.response.send_message(
                    f"**{faction}** の役職データがありません。", ephemeral=True
                )
                return

            view = RoleListView(roles, faction)
            await interaction.response.edit_message(
                content=f"**{faction}** の役職一覧（1/{view.total_pages}ページ）:",
                view=view,
            )
        return callback


class SearchResultView(discord.ui.View):
    def __init__(self, results: list):
        super().__init__(timeout=600)
        for role in results[:25]:
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


# --- スラッシュコマンド ---
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
        "陣営を選んでください:", view=FactionView(), ephemeral=True
    )


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
            "カタカナ・ひらがな・ローマ字で試してみてください。",
            ephemeral=True,
        )
        return

    if len(results) == 1:
        embed = build_role_embed(results[0])
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    await interaction.response.send_message(
        f"**「{keyword}」** の検索結果: {len(results)} 件（最大25件表示）\n役職を選んでください:",
        view=SearchResultView(results),
        ephemeral=True,
    )


# --- on_ready ---
async def refresh_cache() -> None:
    roles = fetch_roles()
    if roles:
        save_cache(roles)
        logger.info("キャッシュ自動更新完了")
    else:
        logger.warning("キャッシュ更新失敗: 既存キャッシュを維持")


@bot.event
async def on_ready():
    logger.info(f"Botログイン: {bot.user}")

    if not load_cache():
        logger.info("キャッシュなし: スクレイピング実行中...")
        roles = fetch_roles()
        if roles:
            save_cache(roles)

    scheduler = AsyncIOScheduler()
    scheduler.add_job(refresh_cache, "cron", hour=0, minute=0)
    scheduler.start()

    await bot.tree.sync()
    logger.info("スラッシュコマンド同期完了")

    threading.Thread(target=run_flask, daemon=True).start()
    logger.info("Flaskヘルスサーバー起動")


if __name__ == "__main__":
    bot.run(load_token())
