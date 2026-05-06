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


if __name__ == "__main__":
    pass
