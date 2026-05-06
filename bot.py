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
    text = jaconv.hira2kata(text)       # ひらがな → カタカナ
    return text


def search_roles(roles: list, keyword: str) -> list:
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


if __name__ == "__main__":
    pass
